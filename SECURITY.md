# Security Policy

## Supported version

Security fixes are applied to the current `main` branch and the active
production-hardening branch.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private
keys, real semiconductor evidence, regulated transaction data, or sensitive
supplier information.

Report privately to the repository owner with:

- affected commit and component;
- reproduction steps;
- expected and actual behaviour;
- impact assessment;
- suggested mitigation, when available.

## Secrets

Never commit `.env`, `.env.production`, API tokens, Fabric identities,
Ethereum keys, mnemonics, certificates, HSM material, production audit data, or
runtime event-store content.

## Deployment warning

The current platform intentionally has no application login or JWT layer. It
must not be exposed directly to the public internet. Use a controlled network,
mTLS or an approved gateway, firewall restrictions, and operating-system access
controls.
