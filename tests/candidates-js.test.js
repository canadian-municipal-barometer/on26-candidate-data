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

// The four field families, and the raw race keys that feed each.
const STEM = {
  mayor: "mayor",
  ward: "coun",
  atlarge: "coun",
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

const censusIds = Object.keys(RAW).filter((k) => k !== "_meta");

// "Wards 1, 5" -> ["Ward 1", "Ward 5"]; the rule the build and ward-links.test.js share.
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

test("no candidate is lost, and none is invented", () => {
  for (const census_id of censusIds) {
    const mun = DATA.municipalities[census_id];
    for (const [ward, entry] of Object.entries(mun.wards)) {
      for (const stem of Object.keys(DATA.meta.max_names)) {
        const expected = expectedFor(census_id, stem, ward)
          .flatMap((r) => r.names)
          .sort();
        assert.deepEqual(
          [...entry.names[stem]].sort(),
          expected,
          `${mun.name} ${ward} ${stem}`,
        );
      }
    }
  }
});

test("a respondent is served their own ward and no other", () => {
  // The failure this guards against is summing a municipality's wards together. Thunder
  // Bay is the case that would show it: five at-large councillors plus the one in the
  // respondent's ward is 6, where all seven wards would total 12.
  const tb = DATA.municipalities["3558004"];
  assert.equal(tb.wards["McIntyre"].fields.coun_max_votes, 6);
  assert.equal(tb.wards["McIntyre"].names.coun.length, 8); // 7 at large + 1 in ward

  // Every ward of every municipality: the councillor list must never contain a name from
  // a different ward's race.
  for (const census_id of censusIds) {
    const races = rawRaces(census_id);
    const mun = DATA.municipalities[census_id];
    for (const [ward, entry] of Object.entries(mun.wards)) {
      const allowed = new Set(
        races
          .filter((r) => r.stem === "coun" && (r.at_large || r.ward === ward))
          .flatMap((r) => r.names),
      );
      for (const name of entry.names.coun) {
        assert.ok(
          allowed.has(name),
          `${mun.name} ${ward}: ${name} is not on this respondent's ballot`,
        );
      }
    }
  }
});

test("Sarnia's two at-large contests both reach every voter", () => {
  // Sarnia has no wards, so both city-wide contests are on one ballot: 4 + 4 marks.
  const sarnia = DATA.municipalities["3538030"];
  assert.deepEqual(Object.keys(sarnia.wards), [AT_LARGE]);
  assert.equal(sarnia.wards[AT_LARGE].fields.coun_max_votes, 8);
  assert.equal(sarnia.wards[AT_LARGE].names.coun.length, 28);
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
      for (const stem of Object.keys(DATA.meta.max_names)) {
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
      for (const stem of Object.keys(DATA.meta.max_names)) {
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
    assert.ok(entry.names.reg_coun.length > 0, "but the candidates are still listed");
  }
});

test("the ballot shape flags describe the councillor race actually served", () => {
  for (const census_id of censusIds) {
    const mun = DATA.municipalities[census_id];
    for (const [ward, entry] of Object.entries(mun.wards)) {
      const races = expectedFor(census_id, "coun", ward);
      const f = entry.fields;
      assert.equal(f.atlarge, Number(races.some((r) => r.at_large)), mun.name + " " + ward);
      assert.equal(
        f.smd,
        Number(races.some((r) => !r.at_large && r.seats === 1)),
        mun.name + " " + ward,
      );
      assert.equal(
        f.mmd,
        Number(races.some((r) => !r.at_large && r.seats > 1)),
        mun.name + " " + ward,
      );
      // Every real ward must have some councillor ballot.
      if (ward !== AT_LARGE) {
        assert.ok(f.smd + f.mmd + f.atlarge >= 1, mun.name + " " + ward + ": no shape");
      }
    }
  }
});

test("Chatham-Kent's two ward tiers differ, and Thunder Bay is both shapes", () => {
  const ck = DATA.municipalities["3536020"].wards;
  assert.equal(ck["Ward 1 - South West Kent"].fields.mmd, 1);
  assert.equal(ck["Ward 1 - South West Kent"].fields.smd, 0);
  assert.equal(ck["Ward 3 - North East Kent"].fields.smd, 1);
  assert.equal(ck["Ward 3 - North East Kent"].fields.mmd, 0);

  const tb = DATA.municipalities["3558004"].wards["McIntyre"].fields;
  assert.equal(tb.atlarge, 1);
  assert.equal(tb.smd, 1);
  // The ward race alone is acclaimed, but the at-large race is not, so there is still a
  // choice to make and the flow must not skip the question.
  assert.equal(tb.coun_accl, 0);
});

test("a ward pair is reachable from either of its wards", () => {
  // Brampton elects both its City and its Regional councillors from ward pairs; a
  // respondent answers with the single ward they live in.
  const b = DATA.municipalities["3521010"].wards;
  assert.deepEqual(b["Ward 1"].names.coun, b["Ward 5"].names.coun);
  assert.deepEqual(b["Ward 1"].names.reg_coun, b["Ward 5"].names.reg_coun);
  assert.notDeepEqual(b["Ward 1"].names.coun, b["Ward 2"].names.coun);
  for (let i = 1; i <= 10; i++) {
    assert.ok(b["Ward " + i], "Brampton has no Ward " + i + " entry");
  }

  // Clarington pairs its Regional seats only, so its four single wards carry over.
  const c = DATA.municipalities["3518017"].wards;
  assert.deepEqual(c["Ward 1"].names.reg_coun, c["Ward 2"].names.reg_coun);
  assert.notDeepEqual(c["Ward 1"].names.coun, c["Ward 2"].names.coun);
});

test("max_names is the longest list any respondent can be served", () => {
  const seen = { mayor: 0, coun: 0, reg_coun: 0, dep_mayor: 0 };
  for (const mun of Object.values(DATA.municipalities)) {
    for (const entry of Object.values(mun.wards)) {
      for (const [stem, names] of Object.entries(entry.names)) {
        seen[stem] = Math.max(seen[stem], names.length);
      }
    }
  }
  assert.deepEqual(seen, DATA.meta.max_names);
});
