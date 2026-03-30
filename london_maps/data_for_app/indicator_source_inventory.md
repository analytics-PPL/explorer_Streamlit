# Indicator source inventory

This file summarises the data sources currently catalogued or live in the app.

## Department for Transport Road Traffic Statistics API
- Status: live_in_app
- Refresh mode: Repeatable API pull
- Geography base: Traffic count points and associated annual traffic statistics
- App usage: Live neighbourhood indicator source
- Source: https://roadtraffic.dft.gov.uk/
- Docs: https://roadtraffic.dft.gov.uk/
- Notes: DfT road traffic API is now live in the app for an advanced sampled traffic-flow context measure based on London count points and link lengths.

## DfE Explore Education Statistics API
- Status: catalogued_only
- Refresh mode: Repeatable API pull
- Geography base: Publication-specific; often school, ward, or local authority
- App usage: Not live in app
- Source: https://explore-education-statistics.service.gov.uk/
- Docs: https://explore-education-statistics.service.gov.uk/data-catalogue
- Notes: Useful only where geography is resident-meaningful or at least ward/local-authority benchmark level; school-only outputs should stay out of the core neighbourhood explorer.

## Environment Agency Flood Monitoring API
- Status: live_in_app
- Refresh mode: Repeatable API pull
- Geography base: Flood areas, stations, and measures
- App usage: Live neighbourhood indicator source
- Source: https://environment.data.gov.uk/flood-monitoring/doc/reference
- Docs: https://environment.data.gov.uk/flood-monitoring/doc/reference
- Notes: Environment Agency flood-area polygons are now live in the app as a contextual neighbourhood flood-overlap share, with careful caveats.

## Indices of Deprivation 2025
- Status: live_in_app
- Refresh mode: Manual file ingest
- Geography base: LSOA 2021
- App usage: Live neighbourhood indicator source
- Source: https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025
- Docs: https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025
- Notes: Ranks and deciles are treated as non-additive display summaries.

## London Air API
- Status: catalogued_only
- Refresh mode: Repeatable API pull
- Geography base: Monitoring sites and forecast areas
- App usage: Not live in app
- Source: https://www.londonair.org.uk/
- Docs: https://api.erg.ic.ac.uk/
- Notes: Strong thematic fit for air-quality context, but station-based data is usually better as benchmark or contextual evidence than as a direct neighbourhood estimate; probe endpoint currently returning 503.

## London Datastore CKAN API
- Status: live_in_app
- Refresh mode: Repeatable ETL discovery or ingest
- Geography base: Partial
- App usage: Live neighbourhood housing and fuel-poverty indicators
- Source: https://data.london.gov.uk/
- Docs: https://data.london.gov.uk/
- Notes: London Datastore is now live in the app for LSOA-backed housing-quality, housing-market, and fuel-poverty context indicators, while ward-only, borough-only, duplicate, and non-LSOA spatial datasets remain catalogued only.

## NHS England Patients Registered at a GP Practice
- Status: live_in_app
- Refresh mode: Repeatable ETL download
- Geography base: LSOA 2021 quarterly outputs plus GP practice / ICB levels
- App usage: Live neighbourhood indicator source
- Source: https://digital.nhs.uk/data-and-information/publications/statistical/patients-registered-at-a-gp-practice
- Docs: https://digital.nhs.uk/data-and-information/publications/statistical/patients-registered-at-a-gp-practice/data-quality-statement
- Notes: Strong neighbourhood-health context source because official LSOA 2021 files can be downloaded and aggregated directly; key caveat is registered population is not the same as resident population.

## NHS England Quality and Outcomes Framework
- Status: live_in_app
- Refresh mode: Refresh local QOF files and rebuild QOF LSOA allocations
- Geography base: GP practice source data allocated to LSOA 2021 via practice-to-LSOA registrations
- App usage: Live neighbourhood QOF prevalence with grouped advanced condition drill-down indicators and annual trend views where history exists
- Source: https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data
- Docs: https://github.com/houseofcommonslibrary/local-health-data-from-QOF
- Notes: The app uses supplied QOF raw files for 2021/22 to 2024/25 plus year-matched GP practice registration support files and Census-based age structure to derive neighbourhood-estimated LSOA indicators across all supported measure families.

## NHS ODS / ORD API
- Status: catalogued_only
- Refresh mode: Repeatable ETL discovery or ingest
- Geography base: No
- App usage: Candidate source only
- Source: https://digital.nhs.uk/services/organisation-data-service/organisation-data-service-apis/choosing-an-organisation-data-service-api
- Docs: https://digital.nhs.uk/services/organisation-data-service/organisation-data-service-apis/choosing-an-organisation-data-service-api
- Notes: Neighbourhood suitability in source discovery: Phase 2.

## NHSBSA Open Data Portal API
- Status: catalogued_only
- Refresh mode: Repeatable ETL discovery or ingest
- Geography base: Mostly no
- App usage: Candidate source only
- Source: https://opendata.nhsbsa.net/
- Docs: https://opendata.nhsbsa.net/
- Notes: Neighbourhood suitability in source discovery: Phase 2.

## NaPTAN / NPTG API
- Status: live_in_app
- Refresh mode: Repeatable API pull
- Geography base: National transport access nodes and gazetteer localities
- App usage: Live neighbourhood indicator source
- Source: https://beta-naptan.dft.gov.uk/
- Docs: https://naptan.api.dft.gov.uk/swagger/index.html
- Notes: NaPTAN access-node API is now live in the app for neighbourhood transport-access counts and density.

## Nomis API
- Status: live_in_app
- Refresh mode: Repeatable ETL discovery or ingest
- Geography base: Yes
- App usage: Live in app for selected LSOA Census indicators, including population, housing, skills, work, ethnicity and health measures via repeatable Nomis API fetches
- Source: https://www.nomisweb.co.uk/api
- Docs: https://www.nomisweb.co.uk/api
- Notes: Neighbourhood suitability in source discovery: Core. Now live for selected LSOA Census indicators at LSOA level; MSOA indicators remain excluded from the public app.

## OHID Fingertips API
- Status: catalogued_only
- Refresh mode: Repeatable ETL discovery or ingest
- Geography base: Partial
- App usage: Metadata discovery and future catalogue only
- Source: https://fingertips.phe.org.uk/profile/guidance
- Docs: https://fingertips.phe.org.uk/profile/guidance
- Notes: Neighbourhood suitability in source discovery: Selective.

## ONS API
- Status: catalogued_only
- Refresh mode: Repeatable ETL discovery or ingest
- Geography base: Partial
- App usage: Candidate benchmark/context source; not live at runtime
- Source: https://developer.ons.gov.uk/
- Docs: https://developer.ons.gov.uk/
- Notes: Neighbourhood suitability in source discovery: Selective.

## ONS Census 2021
- Status: live_in_app
- Refresh mode: Manual file ingest
- Geography base: LSOA 2021
- App usage: Live neighbourhood indicator source
- Source: https://www.ons.gov.uk/census
- Docs: https://www.nomisweb.co.uk/api
- Notes: Current app uses local Census extracts processed to neighbourhood level.

## ONS Open Geography
- Status: catalogued_only
- Refresh mode: Repeatable ETL discovery or ingest
- Geography base: Yes
- App usage: Geography infrastructure source
- Source: https://www.ons.gov.uk/methodology/geography/geographicalproducts/opengeography
- Docs: https://www.ons.gov.uk/methodology/geography/geographicalproducts/opengeography
- Notes: Neighbourhood suitability in source discovery: Infrastructure.

## OpenDataCommunities EPC API
- Status: catalogued_only
- Refresh mode: Credentialed API pull
- Geography base: Certificate-level address data
- App usage: Not live in app
- Source: https://epc.opendatacommunities.org/
- Docs: https://epc.opendatacommunities.org/docs/api
- Notes: Useful for housing-energy context, but the live API is protected and raw certificate records need careful aggregation before public display.

## TfL Unified API
- Status: live_in_app
- Refresh mode: Repeatable API pull
- Geography base: Point features, corridor features, and network metadata
- App usage: Live neighbourhood indicator source
- Source: https://api.tfl.gov.uk/
- Docs: https://api.tfl.gov.uk/
- Notes: TfL BikePoint API is now live in the app for cycle-hire station counts, densities, and dock-capacity context measures.

## data.police.uk API
- Status: catalogued_only
- Refresh mode: Repeatable ETL discovery or ingest
- Geography base: Yes
- App usage: Repeatable route behind current downloaded crime data
- Source: https://data.police.uk/docs/
- Docs: https://data.police.uk/docs/
- Notes: Neighbourhood suitability in source discovery: Core.

## data.police.uk street-level crime
- Status: live_in_app
- Refresh mode: Periodic ETL refresh
- Geography base: Crime event with LSOA code
- App usage: Live neighbourhood indicator source
- Source: https://data.police.uk/docs/
- Docs: https://data.police.uk/docs/
- Notes: Current app uses downloaded monthly London street-crime files and recomputes neighbourhood rates.
