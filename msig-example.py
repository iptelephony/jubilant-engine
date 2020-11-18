#!/usr/bin/env python3
import os
import binascii
import time

from iroha import IrohaCrypto
from iroha import Iroha, IrohaGrpc
from iroha.primitive_pb2 import can_set_my_account_detail, can_set_my_quorum
import sys

if sys.version_info[0] < 3:
    raise Exception('Python 3 or a more recent version is required.')

IROHA_HOST_ADDR = os.getenv('IROHA_HOST_ADDR', '127.0.0.1')
IROHA_PORT = os.getenv('IROHA_PORT', '50051')
ADMIN_ACCOUNT_ID = os.getenv('ADMIN_ACCOUNT_ID', 'admin@test')

ADMIN_PRIVATE_KEY = os.getenv(
    'ADMIN_PRIVATE_KEY', 'f101537e319568c765b2cc89698325604991dca57b9716b58016b253506cab70')
ADMIN_PUBLIC_KEY = IrohaCrypto.derive_public_key(ADMIN_PRIVATE_KEY)

iroha = Iroha(ADMIN_ACCOUNT_ID)
net = IrohaGrpc('{}:{}'.format(IROHA_HOST_ADDR, IROHA_PORT))

# Refinery
GROUP_PRIVATE_KEY='f101537e319568c765b2cc89698325604991dca57b9716b58016b253506caba1'
group = {
'account' : "group@test",
'private_key' : GROUP_PRIVATE_KEY,
'public_key' : IrohaCrypto.derive_public_key(GROUP_PRIVATE_KEY)
}

ALICE_PRIVATE_KEY = 'f101537e319568c765b2cc89698325604991dca57b9716b58016b253506caba2'
alice = {
'account' : "alice@test",
'private_key' : ALICE_PRIVATE_KEY,
'public_key' : IrohaCrypto.derive_public_key(ALICE_PRIVATE_KEY)
}

BOB_PRIVATE_KEY = 'f101537e319568c765b2cc89698325604991dca57b9716b58016b253506caba3'
bob = {
    'account' : "bob@test",
    'private_key' : BOB_PRIVATE_KEY,
    'public_key' : IrohaCrypto.derive_public_key(BOB_PRIVATE_KEY)
}

# Storage
RECEIVER_PRIVATE_KEY = 'f101537e319568c765b2cc89698325604991dca57b9716b58016b253506caba4'
receiver = {
    'account': "receiver@test",
    'private_key': RECEIVER_PRIVATE_KEY,
    'public_key': IrohaCrypto.derive_public_key(RECEIVER_PRIVATE_KEY)
}


def trace(func):
    """
    A decorator for tracing methods' begin/end execution points
    """

    def tracer(*args, **kwargs):
        name = func.__name__
        print('\tEntering "{}"'.format(name))
        result = func(*args, **kwargs)
        print('\tLeaving "{}"'.format(name))
        return result

    return tracer


@trace
def send_transaction_and_print_status(transaction):
    hex_hash = binascii.hexlify(IrohaCrypto.hash(transaction))
    print('Transaction hash = {}, creator = {}'.format(
        hex_hash, transaction.payload.reduced_payload.creator_account_id))
    net.send_tx(transaction)
    for status in net.tx_status_stream(transaction):
        print(status)


def create_account(account_id, key):
    account_id_parts = account_id.split("@")
    return iroha.command('CreateAccount', account_name=account_id_parts[0], domain_id=account_id_parts[1], public_key=key)


@trace
def create_user_accounts():
    tx = iroha.transaction([
        create_account(alice['account'], alice['public_key']),
        create_account(bob['account'], bob['public_key']),
        create_account(group['account'], group['public_key']),
        create_account(receiver['account'], receiver['public_key'])
    ])
    """
    Create users
    """
    IrohaCrypto.sign_transaction(tx, ADMIN_PRIVATE_KEY)
    send_transaction_and_print_status(tx)


@trace
def transfer_coin_from_admin(dest_id, asset_id, amount):
    """
    Transfer asset from admin to another account
    """
    tx = iroha.transaction([
        iroha.command('TransferAsset', src_account_id='admin@test', dest_account_id=dest_id,
                      asset_id=asset_id, description='init top up', amount=amount)
    ])
    IrohaCrypto.sign_transaction(tx, ADMIN_PRIVATE_KEY)
    send_transaction_and_print_status(tx)


@trace
def transfer_coin_from_group(dest_id, asset_id, amount, creator_id, creator_private_key):
    """
    Transfer from the group account to another account.
    This transaction requires 2 sigs to proceed. After the creator has signed, it will be pending.
    """
    src_account_id = group['account']
    iroha2 = Iroha(creator_id)
    tx = iroha2.transaction([
        iroha2.command('TransferAsset', src_account_id=src_account_id, dest_account_id=dest_id,
                      asset_id=asset_id, description='transfer', amount=amount)
    ], creator_account=src_account_id, quorum=2)
    IrohaCrypto.sign_transaction(tx, creator_private_key)
    send_transaction_and_print_status(tx)


@trace
def get_account_assets(account_id):
    """
    List all the assets of userone@domain
    """
    query = iroha.query('GetAccountAssets', account_id=account_id)
    IrohaCrypto.sign_query(query, ADMIN_PRIVATE_KEY)

    response = net.send_query(query)
    data = response.account_assets_response.account_assets
    print('Account = {}'.format(account_id))
    for asset in data:
        print('Asset id = {}, balance = {}'.format(
            asset.asset_id, asset.balance))


@trace
def get_pending_transactions():
    global net
    query = IrohaCrypto.sign_query(Iroha(group['account']).query('GetPendingTransactions'), ADMIN_PRIVATE_KEY)
    pending_transactions = net.send_query(query)
    print(len(pending_transactions.transactions_response.transactions))
    for tx in pending_transactions.transactions_response.transactions:
        print('creator: {}'.format(tx.payload.reduced_payload.creator_account_id))


@trace
def setup_group_account():
    iroha = Iroha(group['account'])
    cmds = [
        iroha.command('AddSignatory', account_id=group['account'], public_key=ADMIN_PUBLIC_KEY),
        iroha.command('AddSignatory', account_id=group['account'], public_key=alice['public_key']),
        iroha.command('AddSignatory', account_id=group['account'], public_key=bob['public_key']),
        iroha.command('GrantPermission', account_id='admin@test', permission=can_set_my_quorum),
    ]
    tx = iroha.transaction(cmds)
    IrohaCrypto.sign_transaction(tx, group['private_key'])
    send_transaction_and_print_status(tx)


@trace
def mint_asset(asset_id, amount):
    """
    Add 1000.00 units of 'coin#domain' to 'usertwo@domain'
    """
    tx = iroha.transaction([
        iroha.command('AddAssetQuantity', asset_id=asset_id, amount=amount)
    ])
    IrohaCrypto.sign_transaction(tx, ADMIN_PRIVATE_KEY)
    send_transaction_and_print_status(tx)


@trace
def sign_pending_transactions(account_id, private_key):
    global net
    query = IrohaCrypto.sign_query(Iroha(account_id).query('GetPendingTransactions'), private_key)
    pending_transactions = net.send_query(query)
    print(len(pending_transactions.transactions_response.transactions))
    for tx in pending_transactions.transactions_response.transactions:
        print('creator: {}'.format(tx.payload.reduced_payload.creator_account_id))
        if tx.payload.reduced_payload.creator_account_id == account_id:
            # we need do this temporarily, otherwise accept will not reach MST engine
            print('tx: {}'.format(tx))
            del tx.signatures[:]
            print('tx: {}'.format(tx))
            IrohaCrypto.sign_transaction(tx, private_key)
            send_transaction_and_print_status(tx)


@trace
def change_quorum(account_id):
    tx = iroha.transaction([
        iroha.command('SetAccountQuorum', account_id=account_id, quorum=2)
    ])
    IrohaCrypto.sign_transaction(tx, ADMIN_PRIVATE_KEY)
    send_transaction_and_print_status(tx)


print('1. creating accounts')
create_user_accounts()
setup_group_account()

print('2. mint coins and give to group#test account')
mint_asset('coin#test', '1000.00')
transfer_coin_from_admin(group['account'], 'coin#test', '42.00')

print('3. alice@test initiates transfer 14.0 from group@test to receiver@test')
transfer_coin_from_group(receiver['account'], 'coin#test', '14.00', alice['account'], alice['private_key'])

print('4. bob@test countersigns transfer')
sign_pending_transactions(group['account'], bob['private_key'])
time.sleep(5)
get_account_assets(receiver['account'])
get_account_assets(group['account'])

print('5. bob@test initiates transfer 7.0 from group@test to receiver@test')
transfer_coin_from_group(receiver['account'], 'coin#test', '7.00', bob['account'], bob['private_key'])

print('6. alice@test countersigns transfer')
sign_pending_transactions(group['account'], alice['private_key'])

time.sleep(5)
get_account_assets(receiver['account'])

get_account_assets(group['account'])


print('done')
