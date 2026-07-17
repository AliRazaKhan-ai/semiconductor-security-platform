package main

import (
	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
	"log"
)

func main() {
	chaincode, err := contractapi.NewChaincode(&ProvenanceContract{})
	if err != nil {
		log.Panicf("create chaincode: %v", err)
	}
	if err := chaincode.Start(); err != nil {
		log.Panicf("start chaincode: %v", err)
	}
}
