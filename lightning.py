"""Public gossip graph only; never pass browser input to lightning-cli."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import subprocess
from threading import Lock
import time


PUBKEY = re.compile(r'(?:02|03)[0-9a-fA-F]{64}')
SCID = re.compile(r'([0-9]{1,8})x([0-9]{1,8})x([0-9]{1,5})')


def valid_scid(value):
    match = SCID.fullmatch(value)
    return bool(match and all(int(part) <= limit for part, limit in
                             zip(match.groups(), (16777215, 16777215, 65535))))


def timestamp(value):
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds')
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def number(value):
    return value if type(value) is int and value >= 0 else None


def capacity(row):
    if number(row.get('satoshis')) is not None:
        return row['satoshis']
    amount = row.get('amount_msat')
    if isinstance(amount, str) and re.fullmatch(r'[0-9]{1,24}msat', amount):
        amount = int(amount[:-4])
    return amount // 1000 if number(amount) is not None else None


def parse_graph(nodes_result, channels_result):
    nodes, channels = {}, {}
    for result, key in ((nodes_result, 'nodes'), (channels_result, 'channels')):
        if not isinstance(result, dict) or not isinstance(result.get(key), list):
            raise ValueError('Invalid graph response')
    for row in nodes_result['nodes']:
        if not isinstance(row, dict) or not isinstance(row.get('nodeid'), str) or not PUBKEY.fullmatch(row['nodeid']):
            raise ValueError('Invalid node')
        pubkey = row['nodeid'].lower()
        addresses = []
        for address in row.get('addresses', []) or []:
            if isinstance(address, dict) and isinstance(address.get('address'), str):
                addresses.append({
                    'type': address.get('type', 'unknown'),
                    'address': address['address'],
                    'port': number(address.get('port')),
                })
        nodes[pubkey] = {
            'pubkey': pubkey,
            'alias': row.get('alias') if isinstance(row.get('alias'), str) else '',
            'addresses': addresses,
            'last_update': timestamp(row.get('last_timestamp')),
        }
    for row in channels_result['channels']:
        if not isinstance(row, dict):
            raise ValueError('Invalid channel')
        if row.get('public') is False:
            continue
        scid = row.get('short_channel_id')
        endpoints = (row.get('source'), row.get('destination'))
        if (not isinstance(scid, str) or not valid_scid(scid)
                or any(not isinstance(key, str) or not PUBKEY.fullmatch(key) for key in endpoints)):
            raise ValueError('Invalid channel')
        source, destination = (key.lower() for key in endpoints)
        for key in (source, destination):
            nodes.setdefault(key, {'pubkey': key, 'alias': '', 'addresses': [], 'last_update': None})
        channel = channels.setdefault(scid, {
            'scid': scid, 'endpoints': sorted((source, destination)),
            'capacity': capacity(row), 'policies': {},
        })
        if channel['endpoints'] != sorted((source, destination)):
            raise ValueError('Conflicting channel endpoints')
        if channel['capacity'] is None:
            channel['capacity'] = capacity(row)
        channel['policies'][source] = {
            'source': source, 'destination': destination,
            'base_fee': number(row.get('base_fee_millisatoshi')),
            'fee_ppm': number(row.get('fee_per_millionth')),
            'cltv_delta': number(row.get('delay')),
            'last_update': timestamp(row.get('last_update')),
        }
    nodes = dict(sorted(nodes.items()))
    channels = dict(sorted(channels.items(), key=lambda item: tuple(map(int, item[0].split('x')))))
    node_channels = {key: [] for key in nodes}
    for channel in channels.values():
        for key in channel['endpoints']:
            node_channels[key].append(channel)
    return {
        'nodes': nodes, 'channels': channels, 'node_channels': node_channels,
        'capacity': sum(channel['capacity'] or 0 for channel in channels.values()),
        'unknown_capacity': sum(channel['capacity'] is None for channel in channels.values()),
        'updated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }


@dataclass(frozen=True)
class GraphState:
    snapshot: dict | None
    status: str


class LightningGraph:
    TTL = 45
    TIMEOUT = 10

    def __init__(self, executable='lightning-cli', lightning_dir=None, network='bitcoin'):
        self.command = [executable]
        if lightning_dir:
            self.command.append(f'--lightning-dir={lightning_dir}')
        self.command.append(f'--network={network}')
        self._lock = Lock()
        self._state = GraphState(None, 'unavailable')
        self._next_refresh = 0

    def _read(self, method):
        if method not in ('listnodes', 'listchannels'):
            raise ValueError('Unsupported public graph method')
        result = subprocess.run(
            [*self.command, method], capture_output=True, text=True,
            timeout=self.TIMEOUT, check=True,
        )
        return json.loads(result.stdout)

    def get(self):
        # A single refresher per worker; other requests never queue behind RPC.
        if not self._lock.acquire(blocking=False):
            return GraphState(self._state.snapshot, 'refreshing')
        try:
            if time.monotonic() < self._next_refresh:
                return self._state
            try:
                snapshot = parse_graph(self._read('listnodes'), self._read('listchannels'))
                self._state = GraphState(snapshot, 'fresh')
            except (OSError, subprocess.SubprocessError, ValueError, TypeError, UnicodeError):
                self._state = GraphState(
                    self._state.snapshot, 'stale' if self._state.snapshot is not None else 'unavailable',
                )
            # Back off failures too, so an outage cannot trigger an RPC storm.
            self._next_refresh = time.monotonic() + self.TTL
            return self._state
        finally:
            self._lock.release()
