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

# The sheet supplies the municipality list plus two attributes carried straight
# through to the output. Fail loudly if a column is renamed, rather than
# silently emitting a column of NA.
sheet_cols <- c("census_id", "provider", "pop_2021")
if (length(setdiff(sheet_cols, names(muns))) > 0) {
  stop(
    "Municipality sheet is missing column(s): ",
    paste(setdiff(sheet_cols, names(muns)), collapse = ", "),
    ". Sheet has: ",
    paste(names(muns), collapse = ", ")
  )
}

# read_sheet() returns a list-column whenever a column holds mixed types (one
# stray text cell in a numeric column is enough). Flatten to plain vectors so
# the join below cannot produce a list-column in the CSV.
flatten_col <- function(x) {
  if (!is.list(x)) {
    return(x)
  }
  x[lengths(x) != 1] <- list(NA)
  unlist(x, use.names = FALSE)
}

muns <- muns |>
  transmute(
    census_id = as.numeric(flatten_col(census_id)),
    provider = as.character(flatten_col(provider)),
    pop_2021 = as.numeric(flatten_col(pop_2021))
  )

if (any(is.na(muns$census_id))) {
  stop(
    "Municipality sheet has ",
    sum(is.na(muns$census_id)),
    " row(s) with no census_id."
  )
}
if (anyDuplicated(muns$census_id) > 0) {
  stop(
    "Duplicate census_id in the municipality sheet: ",
    paste(unique(muns$census_id[duplicated(muns$census_id)]), collapse = ", "),
    ". A duplicate would fan out the join and produce extra output rows."
  )
}

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
# correct master-list row is picked up with all of its attributes. Rewriting
# muns itself (rather than a copy of the ids) keeps provider and pop_2021
# attached to the corrected census_id for the join at the end.
for (i in seq_len(nrow(id_remap))) {
  muns$census_id[muns$census_id == as.numeric(id_remap$old_value[i])] <-
    as.numeric(id_remap$new_value[i])
}
target_ids <- muns$census_id

out <- mun_data |>
  filter(census_id %in% target_ids) |>
  arrange(municipality_name) |>
  select(census_id, csdname, election_type, ward_type)

if (nrow(out) != length(target_ids)) {
  stop(
    "Expected ",
    length(target_ids),
    " municipalities, matched ",
    nrow(out),
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
      "Stale override: ",
      value_overrides$census_id[i],
      " ",
      column,
      " expects old_value '",
      expected,
      "' but cmb_muns.csv now has '",
      current,
      "'. If upstream is already fixed, delete the row from ",
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

# max_votes_source is blank for most races, which read_csv gives back as NA and
# write_csv would then emit as the literal "NA". Normalise once, here, so the
# column round-trips as an empty cell.
races <- races |>
  mutate(max_votes_source = tidyr::replace_na(max_votes_source, ""))

# A race where the voter marks more than one name needs a citation for how many
# -- that number is the whole point of this file and cannot be re-derived from
# seats alone. Single-vote races need none.
uncited <- races |> filter(max_votes > 1, max_votes_source == "")
if (nrow(uncited) > 0) {
  stop(
    "council-races.csv has multiple-vote race(s) with no max_votes_source: ",
    paste0(uncited$csdname, " (", uncited$office, ")", collapse = ", "),
    "."
  )
}

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
    } else {
      ""
    },
    if (length(extra_races) > 0) {
      paste0(" Unexpected: ", paste(extra_races, collapse = ", "), ".")
    } else {
      ""
    }
  )
}

# Integrity check: council seats implied by council-races.csv should equal
# council_size - 1 (i.e. every seat but the mayor's) in the master list. Every
# known deviation is listed here with its cause; anything else is a data error.
seat_exceptions <- tibble::tribble(
  ~census_id , ~reason                                                             ,
     3530010 , "Cambridge: 2 regional councillors sit on Region, not city council" ,
     3530013 , "Kitchener: 4 regional councillors sit on Region, not city council" ,
     3530016 , "Waterloo: 2 regional councillors sit on Region, not city council"  ,
     3536020 , "Chatham-Kent: master council_size is the stale pre-2026 structure" ,
     3528018 , "Haldimand County: master has 6 wards, 2026 uses 7"
)

seat_check <- races |>
  group_by(census_id) |>
  summarise(
    derived_seats = sum(n_districts * seats_per_district),
    .groups = "drop"
  ) |>
  inner_join(select(mun_data, census_id, council_size), by = "census_id") |>
  mutate(delta = derived_seats - (council_size - 1)) |>
  filter(delta != 0, !census_id %in% seat_exceptions$census_id)

if (nrow(seat_check) > 0) {
  stop(
    "Councillor seats in council-races.csv disagree with council_size for: ",
    paste0(
      seat_check$census_id,
      " (",
      seat_check$derived_seats,
      " vs ",
      seat_check$council_size - 1,
      ")",
      collapse = ", "
    ),
    ". Fix the race rows, or add a documented seat_exceptions entry."
  )
}

final <- out |>
  left_join(muns, by = "census_id") |>
  left_join(ballot, by = "census_id") |>
  left_join(revisions, by = "census_id") |>
  mutate(
    revised = tidyr::replace_na(revised, FALSE),
    revision_source = tidyr::replace_na(revision_source, "")
  ) |>
  relocate(provider, pop_2021, .after = csdname)

# Blanks here are a half-filled sheet rather than a broken join, so warn
# instead of aborting -- but say which municipalities, so it is actionable.
for (col in c("provider", "pop_2021")) {
  blank <- final$csdname[is.na(final[[col]])]
  if (length(blank) > 0) {
    warning(
      "No ",
      col,
      " in the sheet for: ",
      paste(blank, collapse = ", "),
      call. = FALSE
    )
  }
}

# Nothing is written until every check below has passed -- see the end of the
# script. A partial write would leave the two generated files disagreeing with
# each other, which is worse than not writing at all.

# ---------------------------------------------------------------------------
# Combined sheet
# ---------------------------------------------------------------------------
# One row per race, with the municipality's attributes repeated across every
# row belonging to that municipality. Generated from `final` and `races`, so
# it cannot drift from either.

mun_cols <- c(
  "provider",
  "pop_2021",
  "election_type",
  "ward_type",
  "block_vote",
  "max_votes_max",
  "revised",
  "revision_source"
)
race_cols <- c(
  "office",
  "deputy_mayor",
  "district_scope",
  "districts",
  "n_districts",
  "seats_per_district",
  "max_votes",
  "max_votes_source",
  "source_url"
)

# csdname lives in both files; joining on census_id alone would silently accept
# a disagreement between them, so check it rather than assume it.
name_check <- races |>
  distinct(census_id, race_name = csdname) |>
  inner_join(select(final, census_id, main_name = csdname), by = "census_id") |>
  filter(race_name != main_name)
if (nrow(name_check) > 0) {
  stop(
    "csdname disagrees between council-races.csv and the municipality list for: ",
    paste0(
      name_check$census_id,
      " ('",
      name_check$race_name,
      "' vs '",
      name_check$main_name,
      "')",
      collapse = ", "
    )
  )
}

combined <- races |>
  select(census_id, csdname, all_of(race_cols)) |>
  left_join(select(final, census_id, all_of(mun_cols)), by = "census_id") |>
  # Municipalities in the same order as the main sheet; races keep their
  # council-races.csv order within each (arrange is stable).
  mutate(.csd = match(census_id, final$census_id)) |>
  arrange(.csd) |>
  select(-.csd) |>
  relocate(all_of(mun_cols), .after = csdname)

# Safety. Denormalising has two failure modes worth guarding: the join fanning
# out or dropping rows, and the repeated municipality values disagreeing with
# each other within a municipality. Both would be easy to miss by eye.
if (nrow(combined) != nrow(races)) {
  stop(
    "Combined sheet has ",
    nrow(combined),
    " rows, expected ",
    nrow(races),
    " (one per race). The join fanned out or dropped rows."
  )
}

back_race <- select(combined, census_id, csdname, all_of(race_cols))
src_race <- select(races, census_id, csdname, all_of(race_cols))
if (nrow(anti_join(back_race, src_race, by = names(back_race))) > 0) {
  stop("Race columns in the combined sheet do not match council-races.csv.")
}

# Collapsing the repeated columns must give back exactly the 38-row sheet. If
# the repetition were inconsistent anywhere, this would yield extra rows.
back_mun <- combined |> select(census_id, all_of(mun_cols)) |> distinct()
src_mun <- select(final, census_id, all_of(mun_cols))
if (
  nrow(back_mun) != nrow(src_mun) ||
    nrow(anti_join(back_mun, src_mun, by = names(back_mun))) > 0
) {
  stop(
    "Municipality columns in the combined sheet do not collapse back to ",
    "election-type-ward-type.csv; the repeated values disagree."
  )
}

# Clean up columns
combined <- combined |>
  select(-all_of(c("max_votes_max", "deputy_mayor"))) |>
  rename(district_source_url = source_url) |>
  relocate(block_vote, .before = max_votes) |>
  relocate(office, .before = election_type) |>
  relocate(revised, revision_source, .before = 1) |>
  relocate(max_votes_source, .after = max_votes) |>
  relocate(district_source_url, .after = seats_per_district)

# ---------------------------------------------------------------------------
# Write, only now that everything has been validated
# ---------------------------------------------------------------------------
readr::write_csv(final, notes("election-type-ward-type.csv"))
readr::write_csv(combined, notes("councillor-election-structure.csv"))
