# EduVulcan for Home Assistant

Custom Home Assistant integration that exposes EduVulcan data as calendar entities using the Iris API.

## Features

- Plan Lekcji (`calendar.eduvulcan_lessons`)
- Zadania Domowe (`calendar.eduvulcan_homework`)
- Egzaminy / Sprawdziany (`calendar.eduvulcan_exams`)

## Installation (HACS)

1. Add this repository as a custom HACS integration repository.
2. Install **EduVulcan for HA**.
3. Restart Home Assistant.

## Configuration

This integration does not use UI credentials. It reads a token from `/config/eduvulcan_token.json`.

Create `/config/eduvulcan_token.json` with the following content:

```json
{
  "jwt": "...",
  "tenant": "...",
  "jwt_payload": {
    "caps": ["EDUVULCAN_PREMIUM"]
  }
}
```

If the token file is missing, incomplete, or lacks the `EDUVULCAN_PREMIUM` capability, the integration will fail to load.

## Usage

Add the integration from **Settings → Devices & Services → Add Integration**, search for **EduVulcan for HA**, and confirm the single setup step.

Calendar entities:

- `calendar.eduvulcan_lessons`
- `calendar.eduvulcan_homework`
- `calendar.eduvulcan_exams`

Homework and exams are always created as all-day events.
