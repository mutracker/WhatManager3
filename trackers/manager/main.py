import asyncio
from logging import Logger
import time

from tornado.platform.asyncio import AsyncIOMainLoop
from tornado.web import Application, url

from WhatManager3.asyncio_helper import JsonWhatManagerRequestHandler
from WhatManager3.settings import TRACKER_MANAGER_PORT
from WhatManager3.utils import db_func
from trackers.loader import get_clients


class TrackerUpdater(object):
    @db_func
    def __init__(self, loop):
        self.loop = loop
        self.logger = Logger('TrackerUpdater')
        self.clients = get_clients()

    def start(self):
        asyncio.async(self.freeleech_update_loop(), loop=self.loop)

    @asyncio.coroutine
    def freeleech_update_loop(self):
        current_time = time.time()
        delay = 1800 - current_time % 1800
        print('Hourly update in ', delay, 's')
        yield from asyncio.sleep(delay)
        print('Starting hourly update')
        for client in self.clients.values():
            update_freeleech = getattr(client, 'update_freeleech', None)
            if update_freeleech is not None:
                try:
                    yield from update_freeleech()
                except Exception as ex:
                    self.logger.error('{0} update_freelech failed with {1}'.format(
                        client.name, ex
                    ))
        print('Hourly update complete')
        asyncio.async(self.freeleech_update_loop(), loop=self.loop)


class AddTorrentHandler(JsonWhatManagerRequestHandler):
    def __init__(self, *args, **kwargs):
        self.updater = kwargs.pop('updater')
        super(AddTorrentHandler, self).__init__(*args, **kwargs)

    @asyncio.coroutine
    def post_json(self):
        tracker_name = self.get_body_argument('tracker')
        torrent_id = self.get_body_argument('id')
        client = self.updater.clients.get(tracker_name, None)
        if client is None:
            return {
                'success': False,
                'error_code': 'tracker_not_found',
                'error': 'Tracker {0} not found'.format(tracker_name),
            }
        body_arguments = {
            k: v[0].decode('utf-8') for k, v in self.request.body_arguments.items()
            if k not in ['tracker', 'id']
        }
        yield from client.fetch_metadata(torrent_id, **body_arguments)
        return {
            'success': True,
        }


def run():
    AsyncIOMainLoop().install()
    loop = asyncio.get_event_loop()
    updater = TrackerUpdater(loop)
    app = Application([
        url('/torrents/add', AddTorrentHandler, kwargs={'updater': updater}),
    ])
    app.listen(TRACKER_MANAGER_PORT)
    loop.call_soon(updater.start)
    loop.run_forever()
