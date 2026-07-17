// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

/// @title HashAnchor
/// @notice Stores only 32-byte cryptographic roots. No semiconductor data or identifiers are accepted.
contract HashAnchor {
    mapping(bytes32 => bool) private anchored;

    error ZeroHash();
    error AlreadyAnchored(bytes32 root);

    event HashAnchored(bytes32 indexed root);

    function anchor(bytes32 root) external {
        if (root == bytes32(0)) revert ZeroHash();
        if (anchored[root]) revert AlreadyAnchored(root);
        anchored[root] = true;
        emit HashAnchored(root);
    }

    function isAnchored(bytes32 root) external view returns (bool) {
        return anchored[root];
    }
}
