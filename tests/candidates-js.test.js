// Checks the served candidate file against the raw data it is built from.
//
// The served file is a lookup table: scripts/build-candidates-js.py works out what every
// respondent is served and stores it, so the survey does not have to. That moves all the
// judgement into the build, and this is where it is checked — that the projection kept
// every candidate, served each respondent their own ward and no one else's, and got the
// acclamation and the vote counts right.
//
// The newest built file is used, so a rebuild is covered without editing this file.
//
// Run from the repo root with:  node --test
// (or point at this file directly; `node --test <dir>` is not supported)

const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync, readdirSync } = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..");
const VERSIONS = path.join(ROOT, "data", "candidate-data-versions");
const RAW_PATH = path.join(ROOT, "data", "raw", "candidates-raw.json");

const AT_LARGE = "99";

// The five field families, and the raw race keys that feed each. One stem is one contest:
// `ward` and `atlarge` are both councillor races but different ballot lines, so they stay
// apart. Mirrors STEM in scripts/build-candidates-js.py.
const STEM = {
  mayor: "mayor",
  ward: "ward",
  atlarge: "atlarge",
  "regional councillor": "reg_coun",
  "deputy mayor": "dep_mayor",
};

function newestBuild() {
  const files = readdirSync(VERSIONS)
    .filter((f) => /^candidates-.*\.js$/.test(f))
    .sort();
  assert.ok(files.length, "no built candidate file in " + VERSIONS);
  return path.join(VERSIONS, files[files.length - 1]);
}

function loadBuilt() {
  const file = newestBuild();
  const sandbox = { window: {} };
  vm.createContext(sandbox);
  vm.runInContext(readFileSync(file, "utf8"), sandbox, { filename: file });
  assert.ok(
    sandbox.window.CMB_CANDIDATES,
    path.basename(file) + " did not assign window.CMB_CANDIDATES",
  );
  // Round-tripped out of the vm realm: objects built inside it carry that realm's
  // prototypes, and assert.deepEqual compares those, so an equal value would still fail.
  return JSON.parse(JSON.stringify(sandbox.window.CMB_CANDIDATES));
}

const DATA = loadBuilt();
const RAW = JSON.parse(readFileSync(RAW_PATH, "utf8"));

// stem -> the field its candidate list is written under. The two are the same word for
// mayor and dep_mayor and differ for all three councillor races, which the survey groups
// under one prefix: ward -> coun_ward, atlarge -> coun_atlarge, reg_coun -> coun_reg. So
// `fields` is keyed by stem and `names` by name field, and this is the map between them —
// read from the data rather than repeated here, and pinned by the test below.
const NAME_FIELD = DATA.meta.stems;
const STEMS = Object.keys(NAME_FIELD);

const censusIds = Object.keys(RAW).filter((k) => k !== "_meta");

// "Wards 1, 5" -> ["Ward 1", "Ward 5"]; the rule the build and parse-wards.test.js share.
function splitWardPair(label) {
  return (label.match(/\d+/g) || []).map((n) => "Ward " + n);
}

// Minimal RFC 4180 reader, returning one object per row keyed by column name. Needed
// because `office` values are quoted and contain a comma ("Councillor, Regional"), which
// naive splitting would shift every later column past. Same splitter as
// structure-csv.test.js; the two files share no module, having no package.json.
function parseCsv(text) {
  const parseLine = (line) => {
    const fields = [];
    let field = "";
    let in_quotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (in_quotes) {
        if (ch !== '"') {
          field += ch;
        } else if (line[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          in_quotes = false;
        }
      } else if (ch === '"') {
        in_quotes = true;
      } else if (ch === ",") {
        fields.push(field);
        field = "";
      } else {
        field += ch;
      }
    }
    fields.push(field);
    return fields;
  };

  const lines = text.split(/\r?\n/).filter((line) => line.trim() !== "");
  const header = parseLine(lines[0]);
  return lines
    .slice(1)
    .map((line) => Object.fromEntries(parseLine(line).map((v, i) => [header[i], v])));
}

// "LAST, First", or bare "LAST" where the source published no given name — display_name()
// in build-candidates-js.py, restated. Keeping the two in step is what makes "no candidate
// is lost, and none is invented" below an assertion about the names rather than about the
// join: it rebuilds every name from the raw data, so any rule the build applies and this
// does not shows up there as a mismatch.
function displayName(candidate) {
  return candidate.first_name
    ? candidate.last_name + ", " + candidate.first_name
    : candidate.last_name;
}

// One ward entry as a respondent meets it. The built file stores it in two halves — the
// municipality's `shared`, holding the races decided for every ward alike, and the ward's
// own — and parse-candidates.js writes both. The halves are disjoint (the build aborts if
// they ever are not), so merging them here cannot lose anything, and it makes the tests
// below assertions about what a respondent is served rather than about where it is kept.
function servedTo(mun, ward) {
  const entry = mun.wards[ward];
  return {
    names: { ...mun.shared.names, ...entry.names },
    fields: { ...mun.shared.fields, ...entry.fields },
  };
}

// Every [ward, served entry] pair of a municipality — what iterating mun.wards used to
// give, before the shared half was lifted out of it.
function servedEntries(mun) {
  return Object.keys(mun.wards).map((ward) => [ward, servedTo(mun, ward)]);
}

// Every scalar the survey writes, across both halves; `meta.fields` is split by level.
const FIELDS = [...DATA.meta.fields.shared, ...DATA.meta.fields.ward];

// Every (stem, ward) a raw race contributes to, with that race's numbers. Mirrors what a
// respondent is served: an at-large race reaches every ward, a ward race only its own.
function rawRaces(census_id) {
  const out = [];
  for (const [race_key, race_list] of Object.entries(RAW[census_id].races)) {
    for (const race of race_list) {
      const at_large = race.district_scope === "At-large";
      for (const [label, district] of Object.entries(race.districts)) {
        const wards =
          race.district_scope === "Ward-pair"
            ? splitWardPair(label)
            : [at_large ? AT_LARGE : label];
        for (const ward of wards) {
          out.push({
            stem: STEM[race_key],
            ward,
            at_large,
            seats: race.seats_per_district,
            max_votes: race.max_votes,
            names: district.candidates.map(displayName),
          });
        }
      }
    }
  }
  return out;
}

// What the raw data says a respondent in `ward` should be served under `stem`.
function expectedFor(census_id, stem, ward) {
  return rawRaces(census_id).filter(
    (r) => r.stem === stem && (r.at_large ? true : r.ward === ward),
  );
}

test("every municipality in the raw data is in the built file, and no others", () => {
  assert.deepEqual(Object.keys(DATA.municipalities).sort(), censusIds.sort());
});

test("every municipality has a 99 entry for a respondent with no ward", () => {
  for (const census_id of censusIds) {
    assert.ok(
      DATA.municipalities[census_id].wards[AT_LARGE],
      census_id + " has no " + AT_LARGE + " entry",
    );
  }
});

test("meta.stems maps every stem to the field its candidates are written under", () => {
  // Two naming schemes meet here: the scalars are named for the race (ward, atlarge,
  // reg_coun), and the candidate lists are grouped under one councillor prefix so the
  // three sort together in the export (coun_ward1, coun_atlarge1, coun_reg1). Nothing
  // downstream can derive one from the other, so the file carries the map and this pins
  // it — a rename on either side that forgets the other shows up here rather than as a
  // question with no candidates in it.
  assert.deepEqual(DATA.meta.stems, {
    mayor: "mayor",
    ward: "coun_ward",
    atlarge: "coun_atlarge",
    reg_coun: "coun_reg",
    dep_mayor: "dep_mayor",
  });

  // Both halves are real: every stem has its scalars, every name field has a list in every
  // entry, and max_names sizes the name fields.
  assert.deepEqual(Object.keys(DATA.meta.max_names).sort(), Object.values(NAME_FIELD).sort());
  for (const mun of Object.values(DATA.municipalities)) {
    for (const [ward, entry] of servedEntries(mun)) {
      assert.deepEqual(
        Object.keys(entry.names).sort(),
        Object.values(NAME_FIELD).sort(),
        mun.name + " " + ward,
      );
      for (const stem of STEMS) {
        assert.ok(
          stem + "_accl" in entry.fields,
          `${mun.name} ${ward}: no ${stem}_accl field`,
        );
      }
    }
  }
});

test("every ward entry carries the same scalar fields", () => {
  const expected = [...FIELDS].sort();
  for (const [census_id, mun] of Object.entries(DATA.municipalities)) {
    for (const [ward, entry] of servedEntries(mun)) {
      assert.deepEqual(
        Object.keys(entry.fields).sort(),
        expected,
        census_id + " " + ward + " writes a different set of fields",
      );
    }
  }
});

// Every scalar is named for the stem it belongs to, so a family reads the same all the
// way through: ward, ward_accl, ward_max_votes, coun_ward1..16. The survey writes these
// names straight out under its own __js_ prefix and renames nothing, so a name that drifts
// here is a column that drifts in the export and a field the Qualtrics flow declares under
// the old spelling. Adding a stem should add its scalars and nothing else — no field list
// to edit, and none of the one-off names a new stem tempts (`has_atlarge`,
// `coun2_max_votes`, a bare `accl` for whichever race seemed the main one).
//
// mayor and dep_mayor are the exception, and the reason they are listed here by hand: both
// are single-seat wherever they appear, so a max_votes for them would be 1 in every row of
// the export and would suggest it might not be. See SINGLE_VOTE_STEMS in the build script.
const SINGLE_VOTE_STEMS = ["mayor", "dep_mayor"];

// The stems that carry a bare `<stem>` served-flag as well as their scalars. The three
// councillor races, because the flow picks between them per respondent and a piped
// `__js_atlarge` says what it means where `__js_atlarge_accl != ""` needs the README. Not
// mayor, which every municipality elects, and not dep_mayor, which is one question rather
// than one of a set. See SERVED_FLAG_STEMS in the build script.
const SERVED_FLAG_STEMS = ["ward", "atlarge", "reg_coun"];

test("every scalar field is named for its stem", () => {
  const stems = STEMS;
  const expected = [
    ...stems.map((stem) => stem + "_accl"),
    ...stems
      .filter((stem) => !SINGLE_VOTE_STEMS.includes(stem))
      .map((stem) => stem + "_max_votes"),
    // the bare served-flags, each completing its own stem's family
    ...SERVED_FLAG_STEMS,
  ].sort();

  assert.deepEqual([...FIELDS].sort(), expected);
});

// `coun`, `smd` and `mmd` were dropped once the flow moved to filtering on the accl and
// max_votes families directly, and so were the bare served-flags — until the three
// councillor ones came back for the flow's sake. Each was exactly derivable from what
// remains, and that is the point of this test either way: a flag that is kept has to keep
// agreeing with the accl it duplicates, or the flow and the export start disagreeing about
// who was served what, and a flag that is gone has to stay gone.
test("the served-flags agree with the accl family, and the dropped flags are derivable", () => {
  for (const census_id of censusIds) {
    const mun = DATA.municipalities[census_id];
    for (const [ward, entry] of servedEntries(mun)) {
      const f = entry.fields;
      const where = `${mun.name} ${ward}`;

      for (const stem of STEMS) {
        // What `<stem>` says, and what a non-blank `<stem>_accl` says: served the race.
        const served = expectedFor(census_id, stem, ward).length > 0;
        if (SERVED_FLAG_STEMS.includes(stem)) {
          assert.equal(f[stem], Number(served), `${where}: ${stem} flag`);
        } else {
          assert.ok(!(stem in f), `${where}: bare ${stem} flag should be gone`);
        }
        assert.equal(
          f[stem + "_accl"] !== "",
          served,
          `${where}: ${stem}_accl blankness no longer tracks served`,
        );
      }

      for (const gone of ["coun", "coun_accl", "coun_max_votes", "smd", "mmd"]) {
        assert.ok(!(gone in f), `${where}: ${gone} should be gone`);
      }
      // What `smd`/`mmd` used to say: the ward race's shape. The `ward` flag itself is
      // checked in the loop above, with the other two.
      const wardRaces = expectedFor(census_id, "ward", ward);
      assert.equal(
        f.ward_max_votes === "" ? 0 : Number(f.ward_max_votes > 1),
        Number(wardRaces.some((r) => r.seats > 1)),
        `${where}: ward_max_votes no longer distinguishes mmd from smd`,
      );
    }
  }
});

// The other half of the claim above: the two stems write no max_votes anywhere, and the
// races behind them really are single-seat. If a municipality ever runs a multi-seat race
// under either, this fails here rather than silently losing the number in the export.
test("mayor and dep_mayor write no max_votes, and never need one", () => {
  for (const stem of SINGLE_VOTE_STEMS) {
    assert.ok(
      !FIELDS.includes(stem + "_max_votes"),
      `${stem}_max_votes should not be declared`,
    );
    for (const census_id of censusIds) {
      const mun = DATA.municipalities[census_id];
      for (const [ward, entry] of servedEntries(mun)) {
        assert.ok(
          !(stem + "_max_votes" in entry.fields),
          `${mun.name} ${ward}: ${stem}_max_votes should not be written`,
        );
        for (const race of expectedFor(census_id, stem, ward)) {
          assert.equal(
            race.max_votes,
            1,
            `${mun.name} ${ward}: ${stem} race is not single-vote`,
          );
        }
      }
    }
  }
});

test("no candidate is lost, and none is invented", () => {
  for (const census_id of censusIds) {
    const mun = DATA.municipalities[census_id];
    for (const [ward, entry] of servedEntries(mun)) {
      for (const stem of STEMS) {
        const expected = expectedFor(census_id, stem, ward)
          .flatMap((r) => r.names)
          .sort();
        assert.deepEqual(
          [...entry.names[NAME_FIELD[stem]]].sort(),
          expected,
          `${mun.name} ${ward} ${stem}`,
        );
      }
    }
  }
});

test("every served name is a display string the survey can read back", () => {
  // The check that does not go through the same join the build uses, and so is the one
  // that catches the next name the join is wrong for. The test above rebuilds every name
  // from the raw data — if it rebuilds it the same wrong way, the two agree and neither
  // says anything. That is exactly what happened to Brampton's `Gursimranjit Singh, -`,
  // published with a placeholder given name: both sides joined an empty first name onto a
  // ", " and both produced "GURSIMRANJIT SINGH, ".
  //
  // It matters beyond looking wrong on the page. These strings are the recognition
  // questions' choice text, and parse-recognition.js reads the selections back by matching
  // them against these same strings verbatim — after trimming the capture. A name whose
  // last character is a space therefore fails to match whenever it is the final selection,
  // and is dropped from `__js_recog_*` with nothing in the export to show it went missing.
  const malformed = new Set();
  for (const [census_id, mun] of Object.entries(DATA.municipalities)) {
    for (const [ward, entry] of servedEntries(mun)) {
      for (const list of Object.values(entry.names)) {
        for (const name of list) {
          if (name !== name.trim() || name === "" || /^,|,$/.test(name)) {
            malformed.add(`${mun.name} (${census_id}) ${ward}: ${JSON.stringify(name)}`);
          }
        }
      }
    }
  }
  assert.deepEqual(
    [...malformed],
    [],
    "names carrying an edge space, or a separator with no name after it",
  );
});

test("a respondent is served their own ward and no other", () => {
  // The failure this guards against is summing a municipality's wards together. Thunder
  // Bay is the case that would show it: its own ward's councillor, never the other six
  // wards', which would total 7 marks rather than 1.
  const tb = DATA.municipalities["3558004"];
  assert.equal(servedTo(tb, "McIntyre").fields.ward_max_votes, 1);
  assert.equal(servedTo(tb, "McIntyre").names.coun_ward.length, 1);

  // Every ward of every municipality: neither councillor list may carry a name from a
  // different ward's race.
  for (const census_id of censusIds) {
    const races = rawRaces(census_id);
    const mun = DATA.municipalities[census_id];
    for (const [ward, entry] of servedEntries(mun)) {
      for (const stem of ["ward", "atlarge"]) {
        const allowed = new Set(
          races
            .filter((r) => r.stem === stem && (r.at_large || r.ward === ward))
            .flatMap((r) => r.names),
        );
        for (const name of entry.names[NAME_FIELD[stem]]) {
          assert.ok(
            allowed.has(name),
            `${mun.name} ${ward} ${stem}: ${name} is not on this respondent's ballot`,
          );
        }
      }
    }
  }
});

test("Sarnia's two city-wide slates are two contests, city and county", () => {
  // Both are elected by every Sarnia voter, four seats each, and they are not the same
  // race: City councillors sit on city council, City-County councillors sit on Lambton
  // County council as well. Merging them would ask one question with 28 names and 8 marks
  // and lose the tier distinction; keeping the upper-tier seat in reg_coun is also what
  // puts a Sarnia respondent's county vote in the same columns as a Waterloo respondent's
  // regional one.
  const sarnia = DATA.municipalities["3538030"];
  assert.deepEqual(Object.keys(sarnia.wards), [AT_LARGE]);
  const { fields, names } = servedTo(sarnia, AT_LARGE);

  assert.equal(fields.atlarge_max_votes, 4);
  assert.equal(names.coun_atlarge.length, 15);
  assert.equal(fields.reg_coun_max_votes, 4);
  assert.equal(names.coun_reg.length, 13);
  assert.deepEqual(
    names.coun_atlarge.filter((n) => names.coun_reg.includes(n)),
    [],
    "a candidate stands in one slate or the other",
  );
});

test("a ward councillor race and an at-large one stay separate contests", () => {
  // max_votes is scoped to its contest: a ward race's is the seats in that ward, and an
  // at-large race's is the whole municipality's, and adding them together would tell a
  // Thunder Bay respondent to mark 6 names in a race that fills one seat. Thunder Bay is
  // the only municipality here that runs both, so it is the only place the two could be
  // conflated — but the stems are split for every municipality, not for this one.
  const tb = servedTo(DATA.municipalities["3558004"], "McIntyre").fields;
  assert.equal(tb.ward, 1);
  assert.equal(tb.ward_max_votes, 1);
  assert.equal(tb.atlarge_max_votes, 5);

  // And the two lists are disjoint everywhere: a name is on one ballot line or the other.
  for (const mun of Object.values(DATA.municipalities)) {
    for (const [ward, entry] of servedEntries(mun)) {
      const overlap = entry.names.coun_ward.filter((n) =>
        entry.names.coun_atlarge.includes(n),
      );
      assert.deepEqual(overlap, [], `${mun.name} ${ward}`);
    }
  }
});

test("at-large councillors are atlarge even with no ward race to collide with", () => {
  // The rule is about scope, not about overlap: Niagara Falls, North Bay and Sarnia elect
  // councillors only at large, and their lists go to atlarge with `ward` left empty,
  // the same as Thunder Bay's at-large seats. A build that special-cased the collision
  // would leave these three under `ward` and put the same office in two different columns
  // depending on whether the municipality happened to have wards.
  for (const [census_id, marks, listed] of [
    ["3526043", 8, null], // Niagara Falls
    ["3548044", 10, null], // North Bay
    ["3538030", 4, 15], // Sarnia: the City slate; its City-County one is reg_coun
  ]) {
    const mun = DATA.municipalities[census_id];
    assert.deepEqual(Object.keys(mun.wards), [AT_LARGE], mun.name);
    const entry = servedTo(mun, AT_LARGE);

    assert.notEqual(entry.fields.atlarge_accl, "", mun.name);
    assert.equal(entry.fields.atlarge_max_votes, marks, mun.name);
    if (listed !== null) {
      assert.equal(entry.names.coun_atlarge.length, listed, mun.name);
    }

    // No ward councillor race at all: blank, not 0, and no ward to report.
    assert.equal(entry.fields.ward, 0, mun.name);
    assert.deepEqual(entry.names.coun_ward, [], mun.name);
    assert.equal(entry.fields.ward_max_votes, "", mun.name);
    assert.equal(entry.fields.ward_accl, "", mun.name);
  }
});

test("PUNCT_ORDER is the order localeCompare actually puts that punctuation in", () => {
  // The build reproduces localeCompare in Python, and this constant is the part of it
  // that had to be found by experiment rather than reasoned out: localeCompare does not
  // order punctuation by code point. Re-derived here, so the constant is checked rather
  // than trusted — the test below only exercises the pairs today's names happen to
  // produce, which would not catch a wrong rank for a pair that never occurs.
  const script = readFileSync(
    path.join(ROOT, "scripts", "build-candidates-js.py"),
    "utf8",
  );
  const match = script.match(/^PUNCT_ORDER = "(.*)"$/m);
  assert.ok(match, "cannot find PUNCT_ORDER in build-candidates-js.py");
  const declared = [...match[1]];

  // Sorted in a letter context, the way the characters are actually met in a name.
  const derived = [...declared].sort((a, b) =>
    ("A" + a + "A").localeCompare("A" + b + "A"),
  );
  assert.deepEqual(
    declared,
    derived,
    "PUNCT_ORDER disagrees with localeCompare: " +
      JSON.stringify(declared.join("")) +
      " vs " +
      JSON.stringify(derived.join("")),
  );

  // The ranks only work because every one of these sorts below any letter; a character
  // that did not would need a rank among the letters instead.
  for (const c of declared) {
    assert.ok(
      ("A" + c + "A").localeCompare("AAA") < 0,
      JSON.stringify(c) + " does not sort below a letter",
    );
  }

  // And the set has to cover the data: the build already fails on a name containing
  // punctuation with no rank, but this says so against the file rather than at build time.
  const used = new Set();
  for (const mun of Object.values(DATA.municipalities)) {
    for (const entry of servedEntries(mun).map(([, entry]) => entry)) {
      for (const list of Object.values(entry.names)) {
        for (const name of list) {
          for (const ch of name) {
            if (!/[\p{L}\p{N}]/u.test(ch)) used.add(ch);
          }
        }
      }
    }
  }
  assert.deepEqual(
    [...used].filter((c) => !declared.includes(c)),
    [],
    "punctuation in the names with no rank in PUNCT_ORDER",
  );
});

test("names are in the order JavaScript's localeCompare produces", () => {
  // The build reproduces localeCompare in Python (see NAME_SORT_KEY). This is the check
  // that the reproduction still holds: a name introducing a character the build has no
  // rank for would sort somewhere localeCompare would not put it.
  for (const [census_id, mun] of Object.entries(DATA.municipalities)) {
    for (const [ward, entry] of servedEntries(mun)) {
      for (const [stem, names] of Object.entries(entry.names)) {
        assert.deepEqual(
          names,
          [...names].sort((a, b) => a.localeCompare(b)),
          `${mun.name} ${ward} ${stem} is not in localeCompare order`,
        );
      }
    }
  }
});

test("acclamation is candidates <= seats, across every race served", () => {
  for (const census_id of censusIds) {
    const mun = DATA.municipalities[census_id];
    for (const [ward, entry] of servedEntries(mun)) {
      for (const stem of STEMS) {
        const races = expectedFor(census_id, stem, ward);
        const expected =
          races.length === 0 || races.some((r) => r.seats === null)
            ? ""
            : Number(races.every((r) => r.names.length <= r.seats));
        assert.equal(
          entry.fields[stem + "_accl"],
          expected,
          `${mun.name} ${ward} ${stem}_accl`,
        );
      }
    }
  }
});

test("max_votes is summed from max_votes, never from seats", () => {
  for (const census_id of censusIds) {
    const mun = DATA.municipalities[census_id];
    for (const [ward, entry] of servedEntries(mun)) {
      for (const stem of STEMS) {
        if (SINGLE_VOTE_STEMS.includes(stem)) continue; // writes no max_votes
        const races = expectedFor(census_id, stem, ward);
        const expected =
          races.length === 0 || races.some((r) => r.max_votes === null)
            ? ""
            : races.reduce((sum, r) => sum + r.max_votes, 0);
        assert.equal(
          entry.fields[stem + "_max_votes"],
          expected,
          `${mun.name} ${ward} ${stem}_max_votes`,
        );
      }
    }
  }
});

test("an excluded contest reaches no respondent, in any ward", () => {
  // notes/excluded-races.csv is the record of what the study leaves out; this is the check
  // that it took effect all the way to the served file. Read from the CSV rather than
  // listed here, so adding a row is covered without editing this test.
  //
  // The drop happens in scripts/build-candidates-raw.py, so the raw file is already clear
  // of these races and the "no candidate was lost" test above cannot see them. Cambridge,
  // Kitchener and Waterloo elect regional councillors who sit on Regional Council rather
  // than city council — not a ballot line the survey asks about.
  const rows = parseCsv(
    readFileSync(path.join(ROOT, "notes", "excluded-races.csv"), "utf8"),
  );
  assert.ok(rows.length, "excluded-races.csv has no rows");

  for (const row of rows) {
    const mun = DATA.municipalities[row.census_id];
    assert.ok(mun, `${row.csdname} is not in the served file at all`);

    const stem = STEM[row.race_key];
    assert.ok(stem, `unknown race_key ${row.race_key} in excluded-races.csv`);

    for (const [ward, entry] of servedEntries(mun)) {
      assert.deepEqual(
        entry.names[NAME_FIELD[stem]],
        [],
        `${row.csdname} ${ward} still serves the excluded ${row.office}`,
      );
      assert.equal(entry.fields[stem + "_accl"], "", `${row.csdname} ${ward} ${stem}`);
      if (!SINGLE_VOTE_STEMS.includes(stem)) {
        assert.equal(entry.fields[stem + "_max_votes"], "");
      }
    }

    // The raw file is where the drop happened, so nothing downstream can reintroduce it.
    const raw = RAW[row.census_id];
    for (const races of Object.values(raw.races)) {
      for (const race of races) {
        assert.notEqual(
          race.office,
          row.office,
          `${row.csdname} ${row.office} is still in candidates-raw.json`,
        );
      }
    }
  }
});

test("the ward flag describes the ward councillor race actually served", () => {
  // The flag describes the ward councillor race only. Whether there is an at-large race is
  // read off atlarge_accl, not from here — see the stem split above.
  for (const census_id of censusIds) {
    const mun = DATA.municipalities[census_id];
    for (const [ward, entry] of servedEntries(mun)) {
      const races = expectedFor(census_id, "ward", ward);
      const f = entry.fields;
      assert.equal(f.ward, Number(races.length > 0), mun.name + " " + ward);

      // Every respondent has a councillor ballot of some kind: their ward's, the
      // municipality's at-large one, or both.
      assert.ok(
        f.ward === 1 || f.atlarge_accl !== "" || ward === AT_LARGE,
        mun.name + " " + ward + ": no councillor race at all",
      );
    }
  }
});

test("Chatham-Kent's two ward tiers differ, and Thunder Bay runs both races", () => {
  // The two tiers are told apart by ward_max_votes now that mmd is gone: six wards elect
  // two councillors on one ballot, the other two elect one.
  const ck = DATA.municipalities["3536020"].wards;
  assert.equal(ck["Ward 1 - South West Kent"].fields.ward_max_votes, 2);
  assert.equal(ck["Ward 3 - North East Kent"].fields.ward_max_votes, 1);
  assert.equal(ck["Ward 1 - South West Kent"].fields.ward, 1);
  assert.equal(ck["Ward 3 - North East Kent"].fields.ward, 1);

  const tb = servedTo(DATA.municipalities["3558004"], "McIntyre").fields;
  assert.equal(tb.ward, 1);
  assert.equal(tb.ward_max_votes, 1);
  assert.notEqual(tb.atlarge_accl, "");
  // Acclamation is per contest now, which is the point of splitting them: this ward's
  // councillor is in unopposed, while the at-large race is contested. Merged, the ward
  // seat's acclamation was invisible — the combined field read 0.
  assert.equal(tb.ward_accl, 1);
  assert.equal(tb.atlarge_accl, 0);
});

test("a ward pair is reachable from either of its wards", () => {
  // Brampton elects both its City and its Regional councillors from ward pairs; a
  // respondent answers with the single ward they live in.
  const b = DATA.municipalities["3521010"].wards;
  assert.deepEqual(b["Ward 1"].names.coun_ward, b["Ward 5"].names.coun_ward);
  assert.deepEqual(b["Ward 1"].names.coun_reg, b["Ward 5"].names.coun_reg);
  assert.notDeepEqual(b["Ward 1"].names.coun_ward, b["Ward 2"].names.coun_ward);
  for (let i = 1; i <= 10; i++) {
    assert.ok(b["Ward " + i], "Brampton has no Ward " + i + " entry");
  }

  // Clarington pairs its Regional seats only, so its four single wards carry over.
  const c = DATA.municipalities["3518017"].wards;
  assert.deepEqual(c["Ward 1"].names.coun_reg, c["Ward 2"].names.coun_reg);
  assert.notDeepEqual(c["Ward 1"].names.coun_ward, c["Ward 2"].names.coun_ward);
});

test("max_names is the longest list any respondent can be served", () => {
  // Counted off the name families the data declares, so a new one is counted rather than
  // skipped. max_names is keyed by name field, since it sizes the numbered fields.
  const seen = Object.fromEntries(Object.values(NAME_FIELD).map((f) => [f, 0]));
  for (const mun of Object.values(DATA.municipalities)) {
    for (const entry of servedEntries(mun).map(([, entry]) => entry)) {
      for (const [stem, names] of Object.entries(entry.names)) {
        seen[stem] = Math.max(seen[stem], names.length);
      }
    }
  }
  assert.deepEqual(seen, DATA.meta.max_names);
});
