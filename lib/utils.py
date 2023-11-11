import functools
import json
import os


import aiohttp
import monarchmoney


DEFAULT_CONFIG_PATH = os.path.expandvars(
    '$HOME/.config/firefly-monarch-config.json',
)


class MonarchStub:

    def __init__(self, monarch, **kwargs):
        self.monarch = monarch
        self.kwargs = kwargs

    async def stub(self, call):
        return self.kwargs.get(call) or await getattr(self.monarch, call)()

    def __getattr__(self, value):
        return functools.partial(self.stub, call=value)


def config(value=None):
    if not value:
        value = DEFAULT_CONFIG_PATH

    with open(value, 'r') as f:
        return json.load(f)


def load_clients(
    dry_run=False,
    firefly_host=None,
    firefly_token=None,
    monarch_session=None,
    global_config=None,
    sync_types=None,
    **kwargs,
):
    if not global_config:
        global_config = config()

    firefly_host = firefly_host or global_config.get('firefly-host')
    firefly_token = firefly_token or global_config.get('firefly-token')
    monarch_session = monarch_session or global_config.get('monarch-session')

    monarch = monarchmoney.MonarchMoney(session_file=monarch_session)

    if kwargs:
        monarch = MonarchStub(monarch, **kwargs)

    return (
        monarch,
        aiohttp.ClientSession(
            base_url=firefly_host,
            headers={
                'Accept': 'application/vnd.api+json',
                'Authorization': f'Bearer {firefly_token}',
            },
        )
    )
