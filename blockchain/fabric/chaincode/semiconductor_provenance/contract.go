package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"regexp"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

var sha256Pattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

type ProvenanceContract struct{ contractapi.Contract }

func timestampUTC(ctx contractapi.TransactionContextInterface) (string, error) {
	timestamp, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return "", err
	}
	return time.Unix(timestamp.Seconds, int64(timestamp.Nanos)).UTC().Format(time.RFC3339Nano), nil
}

func provenanceKey(ctx contractapi.TransactionContextInterface, scanID string) (string, error) {
	return ctx.GetStub().CreateCompositeKey("provenance", []string{scanID})
}

func validateHash(value string) error {
	if !sha256Pattern.MatchString(value) {
		return fmt.Errorf("value is not a lowercase SHA-256 hash")
	}
	return nil
}

func (c *ProvenanceContract) RecordProvenance(ctx contractapi.TransactionContextInterface, scanID, chipID, recordHash, recordJSON string) error {
	if scanID == "" || chipID == "" {
		return fmt.Errorf("scanID and chipID are required")
	}
	if err := validateHash(recordHash); err != nil {
		return fmt.Errorf("recordHash: %w", err)
	}
	digest := sha256.Sum256([]byte(recordJSON))
	if hex.EncodeToString(digest[:]) != recordHash {
		return fmt.Errorf("record hash does not match canonical record JSON")
	}
	key, err := provenanceKey(ctx, scanID)
	if err != nil {
		return err
	}
	existing, err := ctx.GetStub().GetState(key)
	if err != nil {
		return err
	}
	if existing != nil {
		return fmt.Errorf("provenance already exists for scan %s", scanID)
	}
	now, err := timestampUTC(ctx)
	if err != nil {
		return err
	}
	record := ProvenanceRecord{
		DocType: "semiconductorProvenance", ScanID: scanID, ChipID: chipID,
		RecordHash: recordHash, RecordJSON: recordJSON,
		FabricTransactionID: ctx.GetStub().GetTxID(), CreatedAtUTC: now, UpdatedAtUTC: now,
	}
	encoded, err := json.Marshal(record)
	if err != nil {
		return err
	}
	if err := ctx.GetStub().PutState(key, encoded); err != nil {
		return err
	}
	if transient, err := ctx.GetStub().GetTransient(); err == nil {
		if sensitive, ok := transient["sensitiveRecord"]; ok && len(sensitive) > 0 {
			privateKey, keyErr := ctx.GetStub().CreateCompositeKey("sensitive", []string{scanID})
			if keyErr != nil {
				return keyErr
			}
			if err := ctx.GetStub().PutPrivateData("collectionSensitiveEvidence", privateKey, sensitive); err != nil {
				return err
			}
		}
	}
	chipKey, err := ctx.GetStub().CreateCompositeKey("chipScan", []string{chipID, scanID})
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(chipKey, []byte(recordHash))
}

func (c *ProvenanceContract) AttachEthereumAnchor(ctx contractapi.TransactionContextInterface, scanID, rootHash, ethereumTxHash string) error {
	if err := validateHash(rootHash); err != nil {
		return fmt.Errorf("rootHash: %w", err)
	}
	record, key, err := c.load(ctx, scanID)
	if err != nil {
		return err
	}
	if record.EthereumAnchorRoot != "" {
		if record.EthereumAnchorRoot == rootHash && record.EthereumTxHash == ethereumTxHash {
			return nil
		}
		return fmt.Errorf("an Ethereum anchor is already attached")
	}
	now, err := timestampUTC(ctx)
	if err != nil {
		return err
	}
	record.EthereumAnchorRoot = rootHash
	record.EthereumTxHash = ethereumTxHash
	record.UpdatedAtUTC = now
	encoded, err := json.Marshal(record)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(key, encoded)
}

func (c *ProvenanceContract) RevokeProvenance(ctx contractapi.TransactionContextInterface, scanID, reasonHash string) error {
	if err := validateHash(reasonHash); err != nil {
		return fmt.Errorf("reasonHash: %w", err)
	}
	record, key, err := c.load(ctx, scanID)
	if err != nil {
		return err
	}
	now, err := timestampUTC(ctx)
	if err != nil {
		return err
	}
	record.Revoked = true
	record.RevocationReasonHash = reasonHash
	record.UpdatedAtUTC = now
	encoded, err := json.Marshal(record)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(key, encoded)
}

func (c *ProvenanceContract) GetProvenance(ctx contractapi.TransactionContextInterface, scanID string) (*ProvenanceRecord, error) {
	record, _, err := c.load(ctx, scanID)
	return record, err
}

func (c *ProvenanceContract) VerifyRecordHash(ctx contractapi.TransactionContextInterface, scanID, recordHash string) (bool, error) {
	record, _, err := c.load(ctx, scanID)
	if err != nil {
		return false, err
	}
	return record.RecordHash == recordHash, nil
}

func (c *ProvenanceContract) GetChipHistory(ctx contractapi.TransactionContextInterface, chipID string) ([]*ProvenanceRecord, error) {
	iterator, err := ctx.GetStub().GetStateByPartialCompositeKey("chipScan", []string{chipID})
	if err != nil {
		return nil, err
	}
	defer iterator.Close()
	records := []*ProvenanceRecord{}
	for iterator.HasNext() {
		item, err := iterator.Next()
		if err != nil {
			return nil, err
		}
		_, parts, err := ctx.GetStub().SplitCompositeKey(item.Key)
		if err != nil || len(parts) != 2 {
			return nil, fmt.Errorf("invalid chip scan index")
		}
		record, _, err := c.load(ctx, parts[1])
		if err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	return records, nil
}

func (c *ProvenanceContract) GetSensitiveEvidence(ctx contractapi.TransactionContextInterface, scanID string) (string, error) {
	if scanID == "" {
		return "", fmt.Errorf("scanID is required")
	}

	privateKey, err := ctx.GetStub().CreateCompositeKey("sensitive", []string{scanID})
	if err != nil {
		return "", err
	}

	encoded, err := ctx.GetStub().GetPrivateData("collectionSensitiveEvidence", privateKey)
	if err != nil {
		return "", err
	}

	if encoded == nil {
		return "", fmt.Errorf("sensitive evidence not found for scan %s", scanID)
	}

	return string(encoded), nil
}

func (c *ProvenanceContract) GetNetworkMetadata(ctx contractapi.TransactionContextInterface) (map[string]string, error) {
	return map[string]string{"chaincode": "semiconductor-provenance", "schema_version": "1.0"}, nil
}

func (c *ProvenanceContract) load(ctx contractapi.TransactionContextInterface, scanID string) (*ProvenanceRecord, string, error) {
	key, err := provenanceKey(ctx, scanID)
	if err != nil {
		return nil, "", err
	}
	encoded, err := ctx.GetStub().GetState(key)
	if err != nil {
		return nil, "", err
	}
	if encoded == nil {
		return nil, "", fmt.Errorf("provenance not found for scan %s", scanID)
	}
	var record ProvenanceRecord
	if err := json.Unmarshal(encoded, &record); err != nil {
		return nil, "", err
	}
	return &record, key, nil
}
