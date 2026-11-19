# MarketPulse Analytics — Project Instructions

## Project Overview

MarketPulse Analytics is an end-to-end e-commerce sales and marketing intelligence platform.

Its purpose is to analyse sales, advertising, customer behaviour, product performance and business profitability.

## My Background

I operate an e-commerce skincare business.

My business uses:

- Meta Ads messaging campaigns
- WhatsApp
- Instagram
- Shopify
- India Post Speed Post for prepaid orders
- Delhivery for COD orders

Most orders are collected manually through WhatsApp conversations.

I have historical advertising campaign details and WhatsApp order records, but my historical revenue and campaign attribution data are incomplete.

Use this business experience to inspire realistic analytical questions.

Do not assume estimates are actual historical results.

## WhatsApp Order Workflow

- I maintain two WhatsApp groups: Prepaid and COD. Both use the same message format.
- Each order message has: name, address, district/city, PIN code, phone, then products.
- Products are separated by commas. Prepaid: `1 cxe`. COD: `1 cxe(900)`, where 900 is the amount to collect for that line.
- An order with no product line means 1 cream (CXE). Mark it as defaulted.
- Decide COD or prepaid from the source group or explicit payment information.
- Flag missing or uncertain fields for manual review. Never guess.
- The collectible amount is not confirmed revenue.
- Real customer data stays local and private. Never upload it to external AI services or commit it to GitHub.
- Full details: docs/whatsapp_parser_plan.md

## Project Modules

1. Sales Analytics
2. Marketing Analytics
3. Customer Analytics
4. Profitability Analytics
5. Payment and Shipping Analytics

## Technology Stack

Primary technologies:

- Python
- PostgreSQL
- SQL
- Pandas
- NumPy
- Power BI
- Git and GitHub

Optional technologies for later phases:

- FastAPI
- React
- Docker

Do not introduce unnecessary technologies.

## Dataset Rules

- Prefer reliable public datasets.
- Document dataset sources.
- Synthetic datasets must be clearly labelled.
- Never present synthetic data as real business data.
- Do not expose real customer names, phone numbers or addresses.
- Do not invent advertising attribution or business results.

## Development Rules

I am a beginner with Claude Code.

You must:

1. Explain each task before implementing it.
2. Work one small task at a time.
3. Use simple English.
4. Explain the purpose of important files.
5. Explain terminal commands before execution.
6. Do not generate the entire project at once.
7. Do not overwrite existing files without permission.
8. Test your work after implementation.
9. Explain errors and their solutions.
10. Wait for my approval before moving to the next major phase.

## Project Development Phases

Phase 1: Project structure and dataset research.

Phase 2: Database schema and data importing.

Phase 3: Data cleaning using Python and Pandas.

Phase 4: Exploratory Data Analysis.

Phase 5: SQL business analysis.

Phase 6: Power BI dashboard.

Phase 7: Business insights and recommendations.

Phase 8: Documentation and GitHub publication.

Phase 9: Optional API integration and deployment.

## Working Agreement

Before changing files, inspect the existing project.

Explain what you plan to do.

Make small changes.

Show me how to test them.

Do not move forward until I understand and approve the result.

Personal instructions that are not published live in CLAUDE.local.md (ignored by Git).