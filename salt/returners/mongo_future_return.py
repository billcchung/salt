# -*- coding: utf-8 -*-
'''
Return data to a mongodb server

Required python modules: pymongo


This returner will send data from the minions to a MongoDB server. To
configure the settings for your MongoDB server, add the following lines
to the minion config files:

.. cod-block:: yaml

    mongo.db: <database name>
    mongo.host: <server ip address>
    mongo.user: <MongoDB username>
    mongo.password: <MongoDB user password>
    mongo.port: 27017

You can also ask for indexes creation on the most common used fields, which
should greatly improve performance. Indexes are not created by default.

    mongo.indexes: true

Alternative configuration values can be used by prefacing the configuration.
Any values not found in the alternative configuration will be pulled from
the default location:

.. code-block:: yaml

    alternative.mongo.db: <database name>
    alternative.mongo.host: <server ip address>
    alternative.mongo.user: <MongoDB username>
    alternative.mongo.password: <MongoDB user password>
    alternative.mongo.port: 27017


This mongo returner is being developed to replace the default mongodb returner
in the future and should not be considered API stable yet.

To use the mongo returner, append '--return mongo' to the salt command.

.. code-block:: bash

    salt '*' test.ping --return mongo

To use the alternative configuration, append '--return_config alternative' to the salt command.

.. versionadded:: 2015.2.0

.. code-block:: bash

    salt '*' test.ping --return mongo --return_config alternative
'''
from __future__ import absolute_import

# Import python libs
import logging

# Import Salt libs
import salt.utils.jid
import salt.returners
import salt.ext.six as six

# Import third party libs
try:
    import pymongo
    HAS_PYMONGO = True
except ImportError:
    HAS_PYMONGO = False

log = logging.getLogger(__name__)

# Define the module's virtual name
__virtualname__ = 'mongo'


def __virtual__():
    if not HAS_PYMONGO:
        return False
    return __virtualname__


def _remove_dots(src):
    '''
    Remove the dots from the given data structure
    '''
    output = {}
    for key, val in six.iteritems(src):
        if isinstance(val, dict):
            val = _remove_dots(val)
        output[key.replace('.', '-')] = val
    return output


def _get_options(ret=None):
    '''
    Get the mongo options from salt.
    '''
    attrs = {'host': 'host',
             'port': 'port',
             'db': 'db',
             'username': 'username',
             'password': 'password',
             'indexes': 'indexes'}

    _options = salt.returners.get_returner_options(__virtualname__,
                                                   ret,
                                                   attrs,
                                                   __salt__=__salt__,
                                                   __opts__=__opts__)
    return _options


def _get_conn(ret):
    '''
    Return a mongodb connection object
    '''
    _options = _get_options(ret)

    host = _options.get('host')
    port = _options.get('port')
    db_ = _options.get('db')
    user = _options.get('user')
    password = _options.get('password')
    indexes = _options.get('indexes', False)

    conn = pymongo.Connection(host, port)
    mdb = conn[db_]

    if user and password:
        mdb.authenticate(user, password)

    if indexes:
        mdb.saltReturns.ensure_index('minion')
        mdb.saltReturns.ensure_index('jid')

        mdb.jobs.ensure_index('jid')

    return conn, mdb


def returner(ret):
    '''
    Return data to a mongodb server
    '''
    conn, mdb = _get_conn(ret)

    if isinstance(ret['return'], dict):
        back = _remove_dots(ret['return'])
    else:
        back = ret['return']

    if isinstance(ret, dict):
        full_ret = _remove_dots(ret)
    else:
        full_ret = ret

    log.debug(back)
    sdata = {'minion': ret['id'], 'jid': ret['jid'], 'return': back, 'fun': ret['fun'], 'full_ret': full_ret}
    if 'out' in ret:
        sdata['out'] = ret['out']
    # save returns in the saltReturns collection in the json format:
    # { 'minion': <minion_name>, 'jid': <job_id>, 'return': <return info with dots removed>,
    #   'fun': <function>, 'full_ret': <unformatted return with dots removed>}
    mdb.saltReturns.insert(sdata)


def save_load(jid, load):
    '''
    Save the load for a given job id
    '''
    conn, mdb = _get_conn(ret=None)
    mdb.jobs.insert(load)


def get_load(jid):
    '''
    Return the load associated with a given job id
    '''
    conn, mdb = _get_conn(ret=None)
    ret = mdb.jobs.find_one({'jid': jid})
    return ret['load']


def get_jid(jid):
    '''
    Return the return information associated with a jid
    '''
    conn, mdb = _get_conn(ret=None)
    ret = {}
    rdata = mdb.saltReturns.find({'jid': jid})
    if rdata:
        for data in rdata:
            minion = data['minion']
            # return data in the format {<minion>: { <unformatted full return data>}}
            ret[minion] = data['full_ret']
    return ret


def get_fun(fun):
    '''
    Return the most recent jobs that have executed the named function
    '''
    conn, mdb = _get_conn(ret=None)
    ret = {}
    rdata = mdb.saltReturns.find_one({'fun': fun})
    if rdata:
        ret = rdata
    return ret


def get_minions():
    '''
    Return a list of minions
    '''
    conn, mdb = _get_conn(ret=None)
    ret = []
    name = mdb.saltReturns.distinct('minion')
    ret.append(name)
    return ret


def get_jids():
    '''
    Return a list of job ids
    '''
    conn, mdb = _get_conn(ret=None)
    ret = []
    name = mdb.jobs.distinct('jid')
    ret.append(name)
    return ret


def prep_jid(nocache, passed_jid=None):  # pylint: disable=unused-argument
    '''
    Do any work necessary to prepare a JID, including sending a custom id
    '''
    return passed_jid if passed_jid is not None else salt.utils.jid.gen_jid()
