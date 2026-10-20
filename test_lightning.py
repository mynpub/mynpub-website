"""Focused explorer checks, also executed by test_app.py."""

from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
from threading import Event
from unittest.mock import patch

from lightning import GraphState, LightningGraph, parse_graph


KEY_A = '02' + 'ab' * 32
KEY_B = '03' + 'cd' * 32
KEY_C = '02' + 'ef' * 32


def graph_responses():
    nodes = {'nodes': [
        {'nodeid': KEY_A, 'alias': '<script>alert("alias")</script>',
         'last_timestamp': 1700000000,
         'addresses': [{'type': 'ipv4', 'address': '127.0.0.1', 'port': 9735}]},
        {'nodeid': KEY_B, 'alias': 'Beta', 'addresses': []},
    ]}
    policy = {
        'short_channel_id': '100x2x0', 'source': KEY_A, 'destination': KEY_B,
        'amount_msat': '2000000000msat', 'public': True,
        'base_fee_millisatoshi': 0, 'fee_per_millionth': 12,
        'delay': 40, 'last_update': 1700000001,
    }
    channels = {'channels': [
        policy,
        {**policy, 'source': KEY_B, 'destination': KEY_A,
         'base_fee_millisatoshi': 1000, 'fee_per_millionth': 24},
        {'short_channel_id': '101x3x1', 'source': KEY_A, 'destination': KEY_C,
         'satoshis': 3000000},
        {**policy, 'short_channel_id': '102x4x0', 'public': False},
    ]}
    return nodes, channels


def test_lightning_parsing():
    try:
        graph = parse_graph(*graph_responses())
        assert len(graph['nodes']) == 3
        assert len(graph['channels']) == 2
        assert graph['capacity'] == 5000000
        assert len(graph['node_channels'][KEY_A]) == 2
        assert graph['nodes'][KEY_C]['alias'] == ''
        channel = graph['channels']['100x2x0']
        assert channel['capacity'] == 2000000
        assert len(channel['policies']) == 2
        assert channel['policies'][KEY_A]['base_fee'] == 0
        assert channel['policies'][KEY_B]['fee_ppm'] == 24
        assert channel['policies'][KEY_A]['cltv_delta'] == 40
        assert graph['nodes'][KEY_A]['last_update'] == '2023-11-14T22:13:20+00:00'
        assert graph['nodes'][KEY_A]['addresses'][0]['port'] == 9735
        assert parse_graph({'nodes': []}, {'channels': []})['capacity'] == 0
        nodes, channels = graph_responses()
        channels['channels'][0].pop('amount_msat')
        channels['channels'][1]['amount_msat'] = 2000000000
        channels['channels'][2].pop('satoshis')
        graph = parse_graph(nodes, channels)
        assert graph['capacity'] == 2000000
        assert graph['unknown_capacity'] == 1
        assert graph['channels']['101x3x1']['policies'][KEY_A]['base_fee'] is None
        for nodes, channels in (
            ({}, {'channels': []}), ({'nodes': {}}, {'channels': []}),
            ({'nodes': [None]}, {'channels': []}),
            ({'nodes': []}, {'channels': [None]}),
            ({'nodes': []}, {'channels': [{'short_channel_id': '--help'}]}),
        ):
            try:
                parse_graph(nodes, channels)
            except ValueError:
                pass
            else:
                raise AssertionError('Malformed graph accepted')
        print("✓ Lightning graph parsing, deduplication, public filtering, and policies work")
        return True
    except Exception as error:
        print(f"✗ Lightning parsing test failed: {error}")
        return False


def test_lightning_cache():
    try:
        nodes, channels = graph_responses()
        completed = lambda result: subprocess.CompletedProcess([], 0, json.dumps(result), '')
        service = LightningGraph('/usr/local/bin/lightning-cli', '/srv/cln', 'bitcoin')
        with patch('lightning.time.monotonic', return_value=100) as clock, \
                patch('lightning.subprocess.run', side_effect=[completed(nodes), completed(channels)]) as run:
            first = service.get()
            assert first.status == 'fresh'
            assert run.call_count == 2
            assert run.call_args_list[0].args[0] == [
                '/usr/local/bin/lightning-cli', '--lightning-dir=/srv/cln',
                '--network=bitcoin', 'listnodes',
            ]
            assert run.call_args_list[1].args[0][-1] == 'listchannels'
            assert run.call_args.kwargs == {
                'capture_output': True, 'text': True, 'timeout': 10, 'check': True,
            }
            clock.return_value = 144
            assert service.get() is first
            assert run.call_count == 2
            clock.return_value = 145
            run.side_effect = subprocess.TimeoutExpired('lightning-cli', 10)
            stale = service.get()
            assert stale.status == 'stale'
            assert stale.snapshot is first.snapshot
            assert stale.snapshot['updated_at'] == first.snapshot['updated_at']
            assert run.call_count == 3
            clock.return_value = 189
            assert service.get() is stale
            assert run.call_count == 3
            clock.return_value = 190
            run.side_effect = [completed(nodes), completed(channels)]
            assert service.get().status == 'fresh'
            assert run.call_count == 5
        failures = [
            FileNotFoundError(), PermissionError(),
            subprocess.CalledProcessError(1, 'lightning-cli', stderr='private error'),
            subprocess.TimeoutExpired('lightning-cli', 10),
            UnicodeDecodeError('utf8', b'\xff', 0, 1, 'bad byte'),
        ]
        for failure in failures:
            with patch('lightning.subprocess.run', side_effect=failure) as run:
                service = LightningGraph()
                assert service.get().status == 'unavailable'
                assert service.get().snapshot is None
                assert run.call_count == 1
        for output in ('invalid JSON', '{}', '{"nodes": null}', '[]'):
            with patch('lightning.subprocess.run', return_value=subprocess.CompletedProcess([], 0, output, '')):
                assert LightningGraph().get().status == 'unavailable'
        service = LightningGraph()
        with patch.object(service, '_read', side_effect=[nodes, {'channels': 'invalid'}]):
            assert service.get().snapshot is None
        with patch('lightning.subprocess.run') as run:
            try:
                service._read('pay')
            except ValueError:
                pass
            else:
                raise AssertionError('Mutation method accepted')
            run.assert_not_called()
        print("✓ Lightning RPC allowlist, timeout, cache TTL, retry backoff, and stale recovery work")
        return True
    except Exception as error:
        print(f"✗ Lightning cache test failed: {error}")
        return False


def test_lightning_concurrency():
    try:
        service = LightningGraph()
        entered, release = Event(), Event()
        nodes, channels = graph_responses()

        def read(method):
            entered.set()
            assert release.wait(5)
            return nodes if method == 'listnodes' else channels

        with patch.object(service, '_read', side_effect=read) as rpc, \
                ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(service.get)
            try:
                assert entered.wait(5)
                pending = service.get()
                assert pending.status == 'refreshing' and pending.snapshot is None
                assert rpc.call_count == 1
            finally:
                release.set()
            first = future.result(timeout=5)
            assert first.status == 'fresh'
        service._lock.acquire()
        try:
            assert service.get() == GraphState(first.snapshot, 'refreshing')
        finally:
            service._lock.release()
        print("✓ Concurrent visitors do not duplicate or queue behind graph refreshes")
        return True
    except Exception as error:
        print(f"✗ Lightning concurrency test failed: {error}")
        return False


def test_lightning_routes():
    try:
        import app
        graph = parse_graph(*graph_responses())
        with patch.object(app.lightning_graph, 'get', return_value=GraphState(graph, 'fresh')) as get, \
                app.app.test_client() as client:
            response = client.get('/lightning-explorer')
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert '5000000 sat (0.05000000 BTC)' in html
            assert 'Last updated (snapshot)' in html
            assert '&lt;script&gt;' in html and '<script>' not in html
            for query, target in ((KEY_A.upper(), f'node/{KEY_A}'), ('100x2x0', 'channel/100x2x0')):
                response = client.get('/lightning-explorer', query_string={'q': query})
                assert response.status_code == 302
                assert response.location.endswith(target)
            html = client.get('/lightning-explorer', query_string={'q': 'bEtA'}).get_data(as_text=True)
            assert 'Search results (1)' in html and 'Beta' in html
            html = client.get('/lightning-explorer', query_string={'q': '<script>'}).get_data(as_text=True)
            assert '&lt;script&gt;' in html and '<script>' not in html
            html = client.get('/lightning-explorer?q=does-not-exist').get_data(as_text=True)
            assert 'No matching nodes.' in html
            for query in ('x' * 129, 'bad\x00input'):
                get.reset_mock()
                assert client.get('/lightning-explorer', query_string={'q': query}).status_code == 400
                get.assert_not_called()
            for path in ('node/not-a-key', 'channel/1x2x65536', 'channel/16777216x2x0', 'channel/--help'):
                assert client.get('/lightning-explorer/' + path).status_code == 400
            for path in ('node/' + '02' + 'ff' * 32, 'channel/1x1x1'):
                assert client.get('/lightning-explorer/' + path).status_code == 404
            html = client.get('/lightning-explorer/node/' + KEY_A).get_data(as_text=True)
            assert '127.0.0.1:9735' in html and 'Public channels (2)' in html
            assert '2023-11-14T22:13:20+00:00' in html
            assert 'base fee 0 msat' in html and 'fee 24 ppm' in html
            html = client.get('/lightning-explorer/channel/100x2x0').get_data(as_text=True)
            assert KEY_A in html and KEY_B in html
            assert 'Capacity: 2000000 sat' in html and 'CLTV delta 40 blocks' in html
            html = client.get('/lightning-explorer/channel/101x3x1').get_data(as_text=True)
            assert 'base fee Unknown msat' in html and 'Reverse-direction policy unavailable' in html
            for path in ('', '/node/' + KEY_A, '/channel/100x2x0'):
                assert client.post('/lightning-explorer' + path).status_code == 405
        for status, snapshot, expected in (
            ('unavailable', None, 'temporarily unavailable'),
            ('stale', graph, 'data is stale'),
            ('refreshing', None, 'refresh in progress'),
        ):
            with patch.object(app.lightning_graph, 'get', return_value=GraphState(snapshot, status)), \
                    app.app.test_client() as client:
                for path in ('', '/node/' + KEY_A, '/channel/100x2x0'):
                    response = client.get('/lightning-explorer' + path)
                    assert response.status_code == 200
                    assert expected in response.get_data(as_text=True)
        with patch.object(app, 'lightning_graph', LightningGraph()), \
                patch('lightning.subprocess.run', side_effect=subprocess.CalledProcessError(
                    1, 'lightning-cli', stderr='sensitive RPC socket path')), app.app.test_client() as client:
            html = client.get('/lightning-explorer').get_data(as_text=True)
            assert 'temporarily unavailable' in html
            assert 'sensitive RPC socket path' not in html
        print("✓ Explorer search, validation, escaping, details, read-only routes, and failure pages work")
        return True
    except Exception as error:
        print(f"✗ Lightning routes test failed: {error}")
        return False


def test_lightning_pagination():
    try:
        import app
        graph = parse_graph(*graph_responses())
        with patch.object(app.lightning_graph, 'get', return_value=GraphState(graph, 'fresh')), \
                app.app.test_client() as client:
            for query, total in (('kind=nodes', 3), ('kind=channels', 2)):
                for page in range(1, total + 1):
                    response = client.get(f'/lightning-explorer?{query}&per_page=1&page={page}')
                    html = response.get_data(as_text=True)
                    assert response.status_code == 200
                    assert f'Page {page} of {total}' in html
                    assert ('rel="prev"' in html) == (page > 1)
                    assert ('rel="next"' in html) == (page < total)
                    assert html.count('<tr>') == 2
                    assert 'per_page=1' in html
                assert client.get(f'/lightning-explorer?{query}&per_page=1&page={total + 1}').status_code == 404
            html = client.get('/lightning-explorer?per_page=1&q=a').get_data(as_text=True)
            assert 'q=a' in html
            html = client.get(f'/lightning-explorer/node/{KEY_A}?per_page=1&page=2').get_data(as_text=True)
            assert 'Page 2 of 2' in html
            assert '101x3x1' in html and '100x2x0' not in html
            assert f'/lightning-explorer/node/{KEY_A}?' in html
            assert client.get(f'/lightning-explorer/node/{KEY_A}?per_page=1&page=3').status_code == 404
            for query in ('page=0', 'page=-1', 'page=invalid', 'page=1.5', 'page=',
                          'page=' + '9' * 5000, 'per_page=0', 'per_page=101', 'per_page=-1',
                          'per_page=all', 'kind=wallet'):
                assert client.get('/lightning-explorer?' + query).status_code == 400
            assert client.get('/lightning-explorer?per_page=100').status_code == 200
        empty = parse_graph({'nodes': []}, {'channels': []})
        with patch.object(app.lightning_graph, 'get', return_value=GraphState(empty, 'fresh')), \
                app.app.test_client() as client:
            assert 'Page 1 of 1' in client.get('/lightning-explorer').get_data(as_text=True)
            assert client.get('/lightning-explorer?page=2').status_code == 404
        print("✓ Explorer node/channel pagination, links, page size limits, and boundaries work")
        return True
    except Exception as error:
        print(f"✗ Lightning pagination test failed: {error}")
        return False


if __name__ == '__main__':
    checks = (test_lightning_parsing, test_lightning_cache, test_lightning_concurrency,
              test_lightning_routes, test_lightning_pagination)
    raise SystemExit(0 if all([check() for check in checks]) else 1)
