# Changelog

## Initial version

- Terminal searches for Campus Est, floor 1, sectors A and B.
- SUPSI DTI room timetable discovery and weekly-grid import.
- USI Informatics-directory Bachelor/Master discovery and dated calendar import.
- Combined room occupancy with distinct Campus Est/Campus Ovest identifiers.
- Entire-session, availability-at-arrival and daily-gap modes.
- Arrival-before-17:30 rule for entire-session searches.
- Persistent lesson cache, conditional HTTP checks and atomic refreshes.
- Explicit offline mode, fictional demo and custom source configuration.
- Automated offline regression tests and GitHub Actions workflow.

Known limits: SUPSI's published weekly pattern has no dated exceptions; access
permissions and unlisted bookings are not verified. Calendar recurrence rules
and overnight events currently stop import for review. See the README for scope.
