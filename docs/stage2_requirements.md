# Official Stage 2 requirement findings

The two official HackoWatt PDFs were inspected as source-of-truth challenge
documents before this pipeline was designed.

## Common Challenge Assumptions

- Use at least 30 consecutive days of historical data at hourly resolution.
- Use real historical and forecast weather for the scenario location.
- Open-Meteo is explicitly permitted and its Historical Weather API is the
  suggested historical source.
- Include outdoor temperature at minimum.
- Document every added assumption.
- PV production must reflect the assigned scenario location; JRC PVGIS is a
  suggested later-stage PV source.
- The shared tariff and PV economic assumptions belong to later challenge
  stages and are intentionally not implemented here.

## Scenario 3 - Luxury Under Control

- The example household location is Barcelona, Spain.
- Participants must use real historical and forecast weather for Barcelona.
- Outdoor temperature must influence the later historical electricity profile,
  especially heating and air-conditioning demand.
- The later forecast must account for predicted weather and major household
  systems; the later application must show the outdoor-temperature forecast.
- The rooftop PV simulator must be location-specific and compare several system
  capacities, but PV production and economics are outside Stage 2.

## Stage 2 interpretation

The official documents do not mandate additional Stage 2 weather fields beyond
outdoor temperature. This implementation therefore adds only the seven fields
explicitly requested by the project brief: relative humidity, precipitation,
cloud cover, 10 m wind speed, and three horizontal-plane solar-radiation fields.
No household-load, forecast, optimization, PV-production, or economic logic is
included.

