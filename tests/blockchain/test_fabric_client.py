from pathlib import Path
from app.blockchain.fabric.client import CommandResult, FabricClient
from app.blockchain.fabric.identity import FabricIdentity

def test_submit_extracts_transaction_id(tmp_path):
    msp=tmp_path/'msp'; msp.mkdir(); peer=tmp_path/'peer.crt'; peer.write_text('x'); orderer=tmp_path/'orderer.crt'; orderer.write_text('x')
    identity=FabricIdentity('LabMSP',msp,'localhost:7051',peer,'localhost:7050',orderer)
    def runner(command, environment, timeout):
        return CommandResult('', 'Chaincode invoke successful. result: status:200 txid [abcdef1234]', 0)
    client=FabricClient(identity=identity,channel='c',chaincode='cc',runner=runner)
    assert client.submit('F',['a'])=='abcdef1234'
