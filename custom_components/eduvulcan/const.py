"""Constants for the EduVulcan integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "eduvulcan"

PLATFORMS = [Platform.CALENDAR]

TOKEN_FILE = "eduvulcan_token.json"

UPDATE_INTERVAL = timedelta(minutes=60)

KIND_SCHEDULE = "schedule"
KIND_EXAMS = "exams"
KIND_HOMEWORK = "homework"
