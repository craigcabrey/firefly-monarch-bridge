#!/usr/bin/env python3


import argparse
import asyncio
import json
import pprint
import sys
import typing


from lib import models
from lib import utils


async def sync_instances(firefly, firefly_type, monarch):
    monarch_response = await getattr(monarch, firefly_type.MONARCH_API_SYMBOL)()
    monarch_instances = firefly_type.unpack_monarch_response(monarch_response)
    tasks = []

    for monarch_instance in monarch_instances:
        firefly_instance = await firefly_type.from_monarch_instance(
            monarch_instance,
            firefly,
        )

        tasks.append(firefly_instance.create(firefly))

    return await asyncio.gather(*tasks)


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--config',
        default=utils.DEFAULT_CONFIG_PATH,
        dest='global_config',
        type=utils.config,
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument(
        '--sync-types',
        nargs='*',
        choices=[cls.__name__ for cls in models.ALL],
    )

    firefly = parser.add_argument_group()
    firefly.add_argument('--firefly-host')
    firefly.add_argument('--firefly-token')

    monarch = parser.add_argument_group()
    monarch.add_argument('--monarch-session')

    # Debugging options
    monarch.add_argument(
        '--monarch-accounts',
        dest='get_accounts',
        type=utils.config,
    )
    monarch.add_argument(
        '--monarch-categories',
        dest='get_transaction_categories',
        type=utils.config,
    )
    monarch.add_argument(
        '--monarch-tags',
        dest='get_tags',
        type=utils.config,
    )
    monarch.add_argument(
        '--monarch-transactions',
        dest='get_transactions',
        type=utils.config,
    )

    return parser.parse_args()


async def main():
    args = parse_args()
    monarch, firefly = utils.load_clients(**vars(args))

    await monarch.login()

    try:
        for sync_type in set(args.sync_types):
            await sync_instances(firefly, getattr(models, sync_type), monarch)
    finally:
        await firefly.close()

    return True


if __name__ == '__main__':
    sys.exit(0 if asyncio.run(main()) else 1)
