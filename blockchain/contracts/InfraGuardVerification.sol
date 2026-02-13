// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract InfraGuardVerification {
    struct Verification {
        string maintenanceId;
        string assetId;
        bytes32 evidenceHash;
        uint256 timestamp;
    }

    mapping(string => Verification) private verificationByMaintenanceId;

    event MaintenanceVerified(
        string maintenanceId,
        string assetId,
        bytes32 evidenceHash,
        uint256 timestamp
    );

    function recordVerification(
        string calldata maintenanceId,
        string calldata assetId,
        bytes32 evidenceHash
    ) external {
        verificationByMaintenanceId[maintenanceId] = Verification({
            maintenanceId: maintenanceId,
            assetId: assetId,
            evidenceHash: evidenceHash,
            timestamp: block.timestamp
        });

        emit MaintenanceVerified(maintenanceId, assetId, evidenceHash, block.timestamp);
    }

    function getVerification(string calldata maintenanceId)
        external
        view
        returns (Verification memory)
    {
        return verificationByMaintenanceId[maintenanceId];
    }
}
