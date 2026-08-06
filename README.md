# CMB Election Study 2026: Ontario Candidate data

Via Github pages, this repo serves the manually collected candidate data for the Ontario municipalities being studied in the CMB's 2026 Ontario municipal election study.

## Branches

`main` is the production branch used to publish to Github Pages.

`dev` is used to track development before a change is ready to be put into production.

## Key Files and Locations

`data/candidate-data-versions/`: The candidate data that is loaded via the header from this repository's Github pages.

- File format: candidates-{DATE as YYYY-MM-DD}{VERSION}.js`

The date and version number are in the file name and in the file's contents as string constants. Versioning the filename allows for easy downstream access to different versions of the data, which will be useful if the data needs to be updated mid-field. The string constant of the data version makes it easy to extract that information into the final response data, which tracks the version of the data that each respondent saw.

`data/csv/`: The candidate data in CSV form, which gets parsed by `R/parse-js.R` into files in `data/candidate-data-versions/`

- Usage: `R/parse-js.R data/csv/candidates.csv` (or `Rscript R/parse-js.R <csv-file>`). The CSV path is the only argument; it can be run from any working directory.

- This directory also contains mock candidate data for testing, which comes from the CMB's 2025 Alberta election study.
