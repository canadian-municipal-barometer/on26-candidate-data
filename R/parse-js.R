#!/usr/bin/env Rscript

# Wraps a candidate CSV in a JS global (window.CMB_CSV) so it can be served to
# the Qualtrics header via Github pages. Writes a dated, versioned file to
# data/candidate-data-versions/.

usage <- function(con = stdout()) {
  writeLines(
    c(
      "Usage: R/parse-js.R <csv-file>",
      "",
      "Arguments:",
      "  <csv-file>   Path to the candidate data CSV to wrap.",
      "",
      "Options:",
      "  -h, --help   Show this message.",
      "",
      "The version number is read from",
      "data/candidate-data-versions/version.txt, and the output is written to",
      "data/candidate-data-versions/candidates-{YYYY-MM-DD}-v{VERSION}.js"
    ),
    con = con
  )
}

die <- function(...) {
  writeLines(paste0("Error: ", ...), con = stderr())
  quit(status = 1, save = "no")
}

args <- commandArgs(trailingOnly = TRUE)

if (any(args %in% c("-h", "--help"))) {
  usage()
  quit(status = 0, save = "no")
}

if (length(args) != 1) {
  usage(stderr())
  die("expected exactly one argument, got ", length(args), ".")
}

csv_path <- args[[1]]

if (!file.exists(csv_path)) {
  die("no such file: ", csv_path)
}

# Locate the repo root from this script's own path, so the script can be run
# from any working directory.
file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
root <- if (length(file_arg) == 1) {
  # commandArgs() encodes spaces in the script path as "~+~".
  script_path <- gsub("~+~", " ", sub("^--file=", "", file_arg), fixed = TRUE)
  dirname(dirname(normalizePath(script_path)))
} else {
  getwd()
}

version_path <- file.path(root, "data", "candidate-data-versions", "version.txt")

if (!file.exists(version_path)) {
  die("no such file: ", version_path)
}

version <- trimws(readLines(version_path, encoding = "UTF-8")[[1]])

if (is.na(version) || version == "") {
  die("no version number found in ", version_path)
}

csv <- readLines(csv_path, encoding = "UTF-8")

out_path <- file.path(
  root,
  "data",
  "candidate-data-versions",
  paste0("candidates-", format(Sys.Date()), "-v", version, ".js")
)

writeLines(
  text = c("window.CMB_CSV = `", csv, "`;"),
  con = out_path,
  useBytes = TRUE
)

writeLines(paste0("Wrote ", out_path))
