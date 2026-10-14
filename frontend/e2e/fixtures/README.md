# Installation guide fixture

`install-guides.json` is the complete configuration used by the browser smoke
suite. It is an exact snapshot of
[multiapp.json at 4ecd2d5](https://github.com/legiz-ru/my-remnawave/blob/4ecd2d5de6e0ed1879fa2c0a025d6a2b3bd6b592/sub-page/subpage-config/multiapp.json),
captured on 2026-10-14. Git blob: `019ac485b6267ae5c13a112563d64c746f0d26d2`.

Refresh deliberately from a reviewed upstream revision and update this record.
Preserve all platforms, applications, translations, blocks and button types;
do not shrink the payload to make tests pass. The suite still rebuilds current
application sources. Ordinary documentation builds use the upstream URL; only
the browser test server explicitly supplies this fixture.
