library(dplyr)

# Locate the repo root from this script's own path, so the script can be run
# from any working directory. Same idiom as R/parse-js.R.
file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
root <- if (length(file_arg) == 1) {
  # commandArgs() encodes spaces in the script path as "~+~".
  script_path <- gsub("~+~", " ", sub("^--file=", "", file_arg), fixed = TRUE)
  dirname(dirname(normalizePath(script_path)))
} else {
  getwd()
}

# Hand-maintained inputs and the generated output all live in notes/.
notes <- function(...) file.path(root, "notes", ...)

mun_path <- "https://docs.google.com/spreadsheets/d/1QuW7-3GA6_Gbrohr-mUZUH7rhAjUkNs3i6u8rFxda4Y/edit?gid=328183786#gid=328183786" # nolint

muns <- googlesheets4::read_sheet(mun_path)

mun_data_path <- "/Users/reed/Can. Mun. Barometer Dropbox/Reed Merrill/cmb_main/CMB Data/auxiliary-data/Master Municipality List/cmb_muns.csv" # nolint

mun_data <- readr::read_csv(mun_data_path)

# Corrections to the upstream sheet and master list. See SOURCES.md for the
# reasoning and citation behind each one. Rows where column == "census_id"
# remap an ID before the master list is filtered (the sheet points at the wrong
# municipality entirely); all other rows overwrite a column value afterwards.
overrides <- readr::read_csv(
  notes("classification-overrides.csv"),
  col_types = readr::cols(.default = "c")
)

id_remap <- overrides |> filter(column == "census_id")
value_overrides <- overrides |> filter(column != "census_id")

# Point the sheet's IDs at the intended municipalities before filtering, so the
# correct master-list row is picked up with all of its attributes.
target_ids <- muns$census_id
for (i in seq_len(nrow(id_remap))) {
  target_ids[target_ids == as.numeric(id_remap$old_value[i])] <-
    as.numeric(id_remap$new_value[i])
}

out <- mun_data |>
  filter(census_id %in% target_ids) |>
  arrange(municipality_name) |>
  select(census_id, csdname, election_type, ward_type)

if (nrow(out) != length(target_ids)) {
  stop(
    "Expected ", length(target_ids), " municipalities, matched ", nrow(out),
    ". Unmatched IDs: ",
    paste(setdiff(target_ids, out$census_id), collapse = ", ")
  )
}

# Apply the per-column corrections. old_value is a precondition, not a comment:
# once a correction lands upstream in cmb_muns.csv the override becomes a no-op
# that still flags the row as revised, so make it fail instead of rotting.
for (i in seq_len(nrow(value_overrides))) {
  idx <- out$census_id == as.numeric(value_overrides$census_id[i])
  stopifnot(sum(idx) == 1)

  column <- value_overrides$column[i]
  current <- out[[column]][idx]
  expected <- value_overrides$old_value[i]
  # A blank old_value means the master list cell is expected to be empty.
  matched <- if (is.na(expected)) {
    is.na(current)
  } else {
    !is.na(current) && current == expected
  }

  if (!matched) {
    stop(
      "Stale override: ", value_overrides$census_id[i], " ", column,
      " expects old_value '", expected, "' but cmb_muns.csv now has '",
      current, "'. If upstream is already fixed, delete the row from ",
      "classification-overrides.csv; if upstream changed some other way, ",
      "update old_value after rechecking the source."
    )
  }

  out[[column]][idx] <- value_overrides$new_value[i]
}

revisions <- overrides |>
  mutate(census_id = as.numeric(census_id)) |>
  group_by(census_id) |>
  summarise(
    revised = TRUE,
    revision_source = paste(unique(source_url), collapse = " | "),
    .groups = "drop"
  )

# Ballot structure, hand-maintained in council-races.csv (never generated).
# block_vote is derived rather than typed so the two files cannot drift.
races <- readr::read_csv(notes("council-races.csv"), show_col_types = FALSE)
# Several source URLs contain commas and must stay quoted; fail loudly rather
# than silently truncating a field if that quoting is ever lost.
readr::stop_for_problems(races)

ballot <- races |>
  group_by(census_id) |>
  summarise(
    block_vote = any(max_votes > 1),
    max_votes_max = max(max_votes),
    .groups = "drop"
  )

missing_races <- setdiff(out$census_id, ballot$census_id)
extra_races <- setdiff(ballot$census_id, out$census_id)
if (length(missing_races) > 0 || length(extra_races) > 0) {
  stop(
    "council-races.csv is out of sync with the municipality list.",
    if (length(missing_races) > 0) {
      paste0(" Missing: ", paste(missing_races, collapse = ", "), ".")
    } else "",
    if (length(extra_races) > 0) {
      paste0(" Unexpected: ", paste(extra_races, collapse = ", "), ".")
    } else ""
  )
}

# Integrity check: councillor seats implied by council-races.csv should equal
# council_size - 1 (i.e. excluding the mayor) in the master list. Every known
# deviation is listed here with its cause; anything else is a data error.
seat_exceptions <- tibble::tribble(
  ~census_id, ~reason,
  3543014, "Bradford West Gwillimbury: at-large deputy mayor, out of scope",
  3543017, "Innisfil: at-large deputy mayor, out of scope",
  3530010, "Cambridge: 2 regional councillors sit on Region, not city council",
  3530013, "Kitchener: 4 regional councillors sit on Region, not city council",
  3530016, "Waterloo: 2 regional councillors sit on Region, not city council",
  3526053, "St. Catharines: 6 regional councillors sit on Region, not city council",
  3536020, "Chatham-Kent: master council_size is the stale pre-2026 structure",
  3528018, "Haldimand County: master has 6 wards, 2026 uses 7"
)

seat_check <- races |>
  group_by(census_id) |>
  summarise(derived_seats = sum(n_districts * seats_per_district),
            .groups = "drop") |>
  inner_join(select(mun_data, census_id, council_size), by = "census_id") |>
  mutate(delta = derived_seats - (council_size - 1)) |>
  filter(delta != 0, !census_id %in% seat_exceptions$census_id)

if (nrow(seat_check) > 0) {
  stop(
    "Councillor seats in council-races.csv disagree with council_size for: ",
    paste0(seat_check$census_id, " (", seat_check$derived_seats, " vs ",
           seat_check$council_size - 1, ")", collapse = ", "),
    ". Fix the race rows, or add a documented seat_exceptions entry."
  )
}

out |>
  left_join(ballot, by = "census_id") |>
  left_join(revisions, by = "census_id") |>
  mutate(
    revised = tidyr::replace_na(revised, FALSE),
    revision_source = tidyr::replace_na(revision_source, "")
  ) |>
  readr::write_csv(notes("election-type-ward-type.csv"))
