# POC Architecture

## Milestone 1

Browser
  -> Railway Web/API (FastAPI)
  -> PostgreSQL

## Milestone 2

Railway Web/API
  -> Azure Storage Queue
  -> Local Windows CAD Worker
  -> Azure Blob Storage
  -> Railway job status/output URL

## Milestone 3

Local Windows CAD Worker
  -> DriveWorks
  -> SOLIDWORKS
  -> PDF / STEP / drawing / BOM
