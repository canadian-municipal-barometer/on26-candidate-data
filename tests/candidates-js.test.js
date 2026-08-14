// Checks the served candidate file against the raw data it is built from.
//
// The served file is a lookup table: scripts/build-candidates-js.py works out what every
// respondent is served and stores it, so the survey does not have to. That moves all the
// judgement into the build, and this is where it is checked — that the projection kept
// every candidate, served each respondent their own ward and no one else's, and got the
// acclamation, the vote counts and the ballot shape right.
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
  ward: "coun",
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
// under one prefix: coun -> coun_ward, atlarge -> coun_atlarge, reg_coun -> coun_reg. So
// `fields` is keyed by stem and `names` by name field, and this is the map between them —
// read from the data rather than repeated here, and pinned by the test below.
const NAME_FIELD = DATA.meta.stems;
const STEMS = Object.keys(NAME_FIELD);

const censusIds = Object.keys(RAW).filter((k) => k !== "_meta");

// "Wards 1, 5" -> ["Ward 1", "Ward 5"]; the rule the build and parse-wards.test.js share.
function splitWardPair(label) {
  return (label.match(/\d+/g) || []).map((n) => "Ward " + n);
}

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
            names: district.candidates.map((c) => c.last_name + ", " + c.first_name),
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
  // Two naming schemes meet here: the scalars are named for the race (coun, atlarge,
  // reg_coun), and the candidate lists are grouped under one councillor prefix so the
  // three sort together in the export (coun_ward1, coun_atlarge1, coun_reg1). Nothing
  // downstream can derive one from the other, so the file carries the map and this pins
  // it — a rename on either side that forgets the other shows up here rather than as a
  // question with no candidates in it.
  assert.deepEqual(DATA.meta.stems, {
    mayor: "mayor",
    coun: "coun_ward",
    atlarge: "coun_atlarge",
    reg_coun: "coun_reg",
    dep_mayor: "dep_mayor",
  });

  // Both halves are real: every stem has its three scalars, every name field has a list
  // in every entry, and max_names sizes the name fields.
  assert.deepEqual(Object.keys(DATA.meta.max_names).sort(), Object.values(NAME_FIELD).sort());
  for (const mun of Object.values(DATA.municipalities)) {
    for (const [ward, entry] of Object.entries(mun.wards)) {
      assert.deepEqual(
        Object.keys(entry.names).sort(),
        Object.values(NAME_FIELD).sort(),
        mun.name + " " + ward,
      );
      for (const stem of STEMS) {
        assert.ok(stem in entry.fields, `${mun.name} ${ward}: no ${stem} field`);
      }
    }
  }
});

test("every ward entry carries the same scalar fields", () => {
  const expected = [...DATA.meta.fields].sort();
  for (const [census_id, mun] of Object.entries(DATA.municipalities)) {
    for (const [ward, entry] of Object.entries(mun.wards)) {
      assert.deepEqual(
        Object.keys(entry.fields).sort(),
        expected,
        census_id + " " + ward + " writes a different set of fields",
      );
    }
  }
});

// Every scalar is named for the stem it belongs to, so a family reads the same all the
// way through: dep_mayor, dep_mayor_accl, dep_mayor_max_votes, dep_mayor1..3. The survey
// writes these names straight out under its own __js_ prefix and renames nothing, so a
// name that drifts here is a column that drifts in the export and a field the Qualtrics
// flow declares under the old spelling. Adding a stem should add its three scalars and
// nothing else — no field list to edit, and none of the one-off names a new stem tempts
// (`has_atlarge`, `coun2_max_votes`, a bare `accl` for whichever race seemed the main one).
test("every scalar field is named for its stem", () => {
  const stems = STEMS;
  const expected = [
    ...stems, // served this race at all
    ...stems.map((stem) => stem + "_accl"),
    ...stems.map((stem) => stem + "_max_votes"),
    // the ward councillor race's shape, the one pair that belongs to no stem by name
    "smd",
    "mmd",
  ].sort();

  assert.deepEqual([...DATA.meta.fields].sort(), expected);
});

test("no candidate is lost, and none is invented", () => {
  for (const census_id of censusIds) {
    const mun = DATA.municipalities[census_id];
    for (const [ward, entry] of Object.entries(mun.wards)) {
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

test("a respondent is served their own ward and no other", () => {
  // The failure this guards against is summing a municipality's wards together. Thunder
  // Bay is the case that would show it: its own ward's councillor, never the other six
  // wards', which would total 7 marks rather than 1.
  const tb = DATA.municipalities["3558004"];
  assert.equal(tb.wards["McIntyre"].fields.coun_max_votes, 1);
  assert.equal(tb.wards["McIntyre"].names.coun_ward.length, 1);

  // Every ward of every municipality: neither councillor list may carry a name from a
  // different ward's race.
  for (const census_id of censusIds) {
    const races = rawRaces(census_id);
    const mun = DATA.municipalities[census_id];
    for (const [ward, entry] of Object.entries(mun.wards)) {
      for (const stem of ["coun", "atlarge"]) {
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
  const { fields, names } = sarnia.wards[AT_LARGE];

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
  const tb = DATA.municipalities["3558004"].wards["McIntyre"].fields;
  assert.equal(tb.coun, 1);
  assert.equal(tb.coun_max_votes, 1);
  assert.equal(tb.atlarge, 1);
  assert.equal(tb.atlarge_max_votes, 5);

  // And the two lists are disjoint everywhere: a name is on one ballot line or the other.
  for (const mun of Object.values(DATA.municipalities)) {
    for (const [ward, entry] of Object.entries(mun.wards)) {
      const overlap = entry.names.coun_ward.filter((n) =>
        entry.names.coun_atlarge.includes(n),
      );
      assert.deepEqual(overlap, [], `${mun.name} ${ward}`);
    }
  }
});

test("at-large councillors are atlarge even with no ward race to collide with", () => {
  // The rule is about scope, not about overlap: Niagara Falls, North Bay and Sarnia elect
  // councillors only at large, and their lists go to atlarge with `coun` left empty,
  // the same as Thunder Bay's at-large seats. A build that special-cased the collision
  // would leave these three under `coun` and put the same office in two different columns
  // depending on whether the municipality happened to have wards.
  for (const [census_id, marks, listed] of [
    ["3526043", 8, null], // Niagara Falls
    ["3548044", 10, null], // North Bay
    ["3538030", 4, 15], // Sarnia: the City slate; its City-County one is reg_coun
  ]) {
    const mun = DATA.municipalities[census_id];
    assert.deepEqual(Object.keys(mun.wards), [AT_LARGE], mun.name);
    const entry = mun.wards[AT_LARGE];

    assert.equal(entry.fields.atlarge, 1, mun.name);
    assert.equal(entry.fields.atlarge_max_votes, marks, mun.name);
    if (listed !== null) {
      assert.equal(entry.names.coun_atlarge.length, listed, mun.name);
    }

    // No ward councillor race at all: blank, not 0, and no shape to report.
    assert.equal(entry.fields.coun, 0, mun.name);
    assert.deepEqual(entry.names.coun_ward, [], mun.name);
    assert.equal(entry.fields.coun_max_votes, "", mun.name);
    assert.equal(entry.fields.coun_accl, "", mun.name);
    assert.equal(entry.fields.smd + entry.fields.mmd, 0, mun.name);
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
    for (const entry of Object.values(mun.wards)) {
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
    for (const [ward, entry] of Object.entries(mun.wards)) {
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
    for (const [ward, entry] of Object.entries(mun.wards)) {
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
    for (const [ward, entry] of Object.entries(mun.wards)) {
      for (const stem of STEMS) {
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

test("an unverified seat count leaves the fields blank rather than guessing", () => {
  // Kitchener and Cambridge each publish an at-large regional race with no verified seat
  // count upstream; see the structure_gap notes in data/raw/by-municipality/.
  for (const census_id of ["3530013", "3530010"]) {
    const entry = DATA.municipalities[census_id].wards["Ward 1"];
    assert.equal(entry.fields.reg_coun_accl, "");
    assert.equal(entry.fields.reg_coun_max_votes, "");
    assert.ok(entry.names.coun_reg.length > 0, "but the candidates are still listed");
  }
});

test("the ballot shape flags describe the ward councillor race actually served", () => {
  // smd and mmd describe the `coun` race only. Whether there is an at-large councillor
  // race is atlarge's own flag, not a third shape — see the stem split above.
  for (const census_id of censusIds) {
    const mun = DATA.municipalities[census_id];
    for (const [ward, entry] of Object.entries(mun.wards)) {
      const races = expectedFor(census_id, "coun", ward);
      const f = entry.fields;
      assert.equal(f.smd, Number(races.some((r) => r.seats === 1)), mun.name + " " + ward);
      assert.equal(f.mmd, Number(races.some((r) => r.seats > 1)), mun.name + " " + ward);
      assert.ok(f.smd + f.mmd <= 1, mun.name + " " + ward + ": two shapes at once");

      // Every respondent has a councillor ballot of some kind: their ward's, the
      // municipality's at-large one, or both.
      assert.ok(
        f.coun + f.atlarge >= 1 || ward === AT_LARGE,
        mun.name + " " + ward + ": no councillor race at all",
      );
    }
  }
});

test("Chatham-Kent's two ward tiers differ, and Thunder Bay runs both races", () => {
  const ck = DATA.municipalities["3536020"].wards;
  assert.equal(ck["Ward 1 - South West Kent"].fields.mmd, 1);
  assert.equal(ck["Ward 1 - South West Kent"].fields.smd, 0);
  assert.equal(ck["Ward 3 - North East Kent"].fields.smd, 1);
  assert.equal(ck["Ward 3 - North East Kent"].fields.mmd, 0);

  const tb = DATA.municipalities["3558004"].wards["McIntyre"].fields;
  assert.equal(tb.smd, 1);
  assert.equal(tb.atlarge, 1);
  // Acclamation is per contest now, which is the point of splitting them: this ward's
  // councillor is in unopposed, while the at-large race is contested. Merged, the ward
  // seat's acclamation was invisible — the combined field read 0.
  assert.equal(tb.coun_accl, 1);
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
    for (const entry of Object.values(mun.wards)) {
      for (const [stem, names] of Object.entries(entry.names)) {
        seen[stem] = Math.max(seen[stem], names.length);
      }
    }
  }
  assert.deepEqual(seen, DATA.meta.max_names);
});
