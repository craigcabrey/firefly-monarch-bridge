#!/usr/bin/env python3


import argparse
import asyncio
import json
import logging
import pprint
import sys
import typing


from lib import models
from lib import utils


logger = logging.getLogger('firefly-monarch-bridge')
logging.setLogRecordFactory(utils.LogRecord)
logging.basicConfig(
    format='[{asctime}] {levelname:<8} {source:<30} {message}',
    level=logging.INFO,
    style='{',
)


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
    sync_types = [cls.__name__ for cls in models.ALL]

    parser.add_argument(
        '--config',
        dest='global_config',
        type=utils.config,
    )
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument(
        '--sync-types',
        nargs='+',
        choices=sync_types,
        default=sync_types,
    )

    firefly = parser.add_argument_group()
    firefly.add_argument('--firefly-host')
    firefly.add_argument('--firefly-token')

    monarch = parser.add_argument_group()
    monarch.add_argument('--monarch-session')

    for type in models.ALL:
        monarch.add_argument(
            f'--monarch-{type.MONARCH_UNPACK_KEY}',
            dest=type.MONARCH_API_SYMBOL,
            type=utils.config,
        )

    return parser.parse_args()


async def main():
    args = parse_args()

    if args.debug or args.dry_run:
        logger.setLevel(logging.DEBUG)

    monarch, firefly = utils.load_clients(**vars(args))
    logger.debug('Sync types: %s', args.sync_types)

    await monarch.login()

    try:
        for sync_type in set(args.sync_types):
            await sync_instances(firefly, getattr(models, sync_type), monarch)
    finally:
        await firefly.close()

    return True


if __name__ == '__main__':
    sys.exit(0 if asyncio.run(main()) else 1)
