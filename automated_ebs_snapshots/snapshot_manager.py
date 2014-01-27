""" Module handling the snapshots """
import logging
import datetime
import time

from automated_ebs_snapshots import volume_manager
from automated_ebs_snapshots.valid_intervals import VALID_INTERVALS

logger = logging.getLogger(__name__)


def run(connection, interval=60):
    """ Ensure that we have snapshots for a given volume

    :type connection: boto.ec2.connection.EC2Connection
    :param connection: EC2 connection object
    :type interval: int
    :param interval: Number of seconds to wait between checks
    """
    while True:
        volumes = volume_manager.get_watched_volumes(connection)

        for volume in volumes:
            _ensure_snapshot(connection, volume)

        logger.info('Waiting {} seconds until next check'.format(interval))
        time.sleep(interval)


def _create_snapshot(volume):
    """ Create a new snapshot

    :type volume: boto.ec2.volume.Volume
    :param volume: Volume to snapshot
    :returns: boto.ec2.snapshot.Snapshot -- The new snapshot
    """
    logger.info('Creating new snapshot for {}'.format(volume.id))
    snapshot = volume.create_snapshot(
        description="Automatic snapshot by Skymill Auto EBS")
    logger.info('Created snapshot {} for volume {}'.format(
        snapshot.id, volume.id))

    return snapshot


def _ensure_snapshot(connection, volume):
    """ Ensure that a given volume has an appropriate snapshot

    :type connection: boto.ec2.connection.EC2Connection
    :param connection: EC2 connection object
    :type volume: boto.ec2.volume.Volume
    :param volume: Volume to check
    """
    if 'AutomatedEBSSnapshots' not in volume.tags:
        logger.warning(
            'Missing tag AutomatedEBSSnapshots for volume {}'.format(
                volume.id))
        return

    interval = volume.tags['AutomatedEBSSnapshots']
    if volume.tags['AutomatedEBSSnapshots'] not in VALID_INTERVALS:
        logger.warning(
            '"{}" is not a valid snapshotting interval for volume {}'.format(
                interval, volume.id))
        return

    snapshots = connection.get_all_snapshots(filters={'volume-id': volume.id})

    # Create a snapshot if we don't have any
    if not snapshots:
        _create_snapshot(volume)
        return

    min_delta = 3600*24*365*10  # 10 years :)
    for snapshot in snapshots:
        timestamp = datetime.datetime.strptime(
            snapshot.start_time,
            '%Y-%m-%dT%H:%M:%S.000Z')
        delta_seconds = int(
            (datetime.datetime.utcnow() - timestamp).total_seconds())

        if delta_seconds < min_delta:
            min_delta = delta_seconds

    logger.info('The newest snapshot for {} is {} seconds old'.format(
        volume.id, min_delta))
    if interval == 'hourly' and min_delta > 3600:
        _create_snapshot(volume)
    elif interval == 'daily' and min_delta > 3600*24:
        _create_snapshot(volume)
    elif interval == 'weekly' and min_delta > 3600*24*7:
        _create_snapshot(volume)
    elif interval == 'monthly' and min_delta > 3600*24*30:
        _create_snapshot(volume)
    elif interval == 'yearly' and min_delta > 3600*24*365:
        _create_snapshot(volume)
