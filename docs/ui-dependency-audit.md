# UI dependency audit (2026-11-10)

Scope: Vue 2.7 / NS8 UI library 2.2.1; no framework or Carbon migration.

## Safe correction

`node-gyp/undici` is resolved to 8.12.2, within node-gyp's declared `^8.4.1`
range. This updates build tooling only, not the browser HTTP client (Axios).
Undici 8.11.2 had eight advisories, including TLS validation bypass,
cross-origin cache disclosure and denial of service. The test resolves Undici
from node-gyp, checks the patched major/version and exercises a local HTTP fetch.
It failed on 8.11.2 before the change and passes on 8.12.2. Node 24.22.2 meets
Undici's Node >=22.19.0 requirement. Remove the override once an ordinary lockfile
refresh selects a fixed version without it.

`yarn npm audit --all --recursive --json` before/after:

| Findings | Before | After |
| --- | ---: | ---: |
| Security advisories (excluding deprecation notices) | 13 | 5 |
| High | 7 | 3 |
| Moderate | 4 | 0 |
| Low | 2 | 2 |
| Deprecation notices | 6 | 6 |

The audit still exits nonzero; this is not a zero-vulnerability claim.
Minimatch resolves to 3.1.5 and has no advisory in this audit; no unrelated
major-version override was added.

## Retained dependencies and warnings

Usage was checked in both `ui/src` and the installed
`node_modules/@nethserver/ns8-ui-lib` sources/ESM bundle before considering removal:

- `lottie-web-vue`: library `NsLottieAnimation` imports it; `NsEmptyState`
  renders that component. Keep it and the existing registration. The Lottie
  `eval` build warning remains; hiding it or swapping animation players would
  not be a behavior-neutral dependency cleanup.
- `vue-axios`: the library's task service calls `this.axios.get/post`, provided
  by the app's `Vue.use(VueAxios, axios)`. Removing the plugin would break NS8
  task transport even though views do not import it directly.
- `vue-debounce`: the library's `NsDataTable` and `NsComboSearchBox` use
  `v-debounce`. Keep the globally registered directive.
- The missing `/cluster-admin/css/core.css` at build time is intentional:
  the NS8 host provides it at runtime. No CJS/ESM warning was observed.

Install peer warnings are unchanged and not suppressed:

- ESLint 6.8.0 satisfies eslint-plugin-vue 6's `^5 || ^6`, but the current
  Babel ESLint parser requires `^7.5 || ^8 || ^9`. These ranges do not overlap;
  packageExtensions cannot truthfully fix this compatibility issue. A coordinated
  lint-toolchain upgrade is separate work.
- The published NS8 library ships `@rollup/plugin-json` as a dependency without
  providing its Rollup build peer. The application consumes the prebuilt library,
  not its Rollup build. No fabricated optional peer or unused Rollup installation
  was added to silence the upstream metadata warning.

Remaining security advisories:

- `flatted@2.0.2`, via ESLint's `flat-cache@2.0.1`: GHSA-25h7-pfq9-p65f and
  GHSA-rf6f-7fwh-wjgh (high). Fix requires leaving the declared `^2.0.0` range.
- `tmp@0.0.33`, via ESLint/Inquirer `external-editor@3.1.0`:
  GHSA-52f5-9888-hmc6 (low), GHSA-ph9p-34f9-6g65 (high). Fixed releases are
  outside the declared `^0.0.33` range. These and Flatted are lint tooling,
  not browser payloads; do not process untrusted lint caches/editor input.
- `vue@2.7.16`: GHSA-5j4c-8p2g-v4jx (low), compiler parseHTML ReDoS.
  The application uses precompiled Vue SFCs, but the advisory is retained;
  a Vue/Carbon stack migration was explicitly excluded from this work.

## Checks

Locally: immutable install, lint, four Node tests, production build succeeded;
Python suite: 53 tests, one dependency-gated integration skip. Browser output
filenames/hashes are unchanged after the tooling-only update. CI additionally
runs the full NS8 Debian/Rocky install/update matrix; see the PR checks and
release evidence for the exact tested commits, not this local check list.
