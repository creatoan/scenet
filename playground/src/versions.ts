/**
 * Which version of Scenet this playground runs, and the way to the others.
 *
 * Every version of the site carries a playground: the latest release's at the root,
 * main's under /dev/, each minor version's under /vX.Y/. The page is the same in each and
 * nothing in it says which it is, but its address does. The version switcher's data --
 * the one switcher.json every version of the documentation reads -- names the address of
 * each version, and a version's playground is `playground/` under it.
 *
 * The file is fetched, so what it holds is checked before it is used. Served from
 * anywhere else, as under `npm run dev`, there is no such file, and the page shows no
 * version rather than a wrong one.
 */

/** The version switcher's data, at the one address every version of the site reads. */
export const SWITCHER_URL = "/scenet/switcher.json";

/** An entry of switcher.json, as pydata-sphinx-theme's version switcher reads it. */
export interface Version {
  readonly name: string;
  readonly version: string;
  /** Where the version is served: a path on this site, ending in `/`. */
  readonly url: string;
  /** The latest release; exactly one entry has it. */
  readonly preferred?: boolean;
}

/** The entries of a fetched switcher.json; anything that is not one is dropped. */
export function parseVersions(data: unknown): Version[] {
  if (!Array.isArray(data)) return [];
  const versions: Version[] = [];
  for (const entry of data as unknown[]) {
    if (typeof entry !== "object" || entry === null) continue;
    const { name, version, url, preferred } = entry as Record<string, unknown>;
    if (typeof name !== "string" || typeof version !== "string" || typeof url !== "string") {
      continue;
    }
    // A path on this site only: the page links to it, and its CSP allows nothing else.
    if (!url.startsWith("/") || url.startsWith("//") || !url.endsWith("/")) continue;
    versions.push(preferred === true ? { name, version, url, preferred } : { name, version, url });
  }
  return versions;
}

/** Where a version's playground is, carrying a share link's document along. */
export function playgroundUrl(version: Version, hash: string): string {
  return `${version.url}playground/${hash}`;
}

/**
 * The version a playground at `pathname` runs.
 *
 * The longest address wins: the latest release's, `/scenet/`, is a prefix of every other.
 */
export function currentVersion(versions: readonly Version[], pathname: string): Version | undefined {
  let found: Version | undefined;
  for (const version of versions) {
    const own = playgroundUrl(version, "");
    if (pathname.startsWith(own) && (found === undefined || version.url.length > found.url.length)) {
      found = version;
    }
  }
  return found;
}

/** What to tell somebody in a playground that is not the latest release's. */
export interface Banner {
  readonly text: string;
  readonly latest: Version;
}

/** The banner for `current`, or none on the latest release -- the documentation's rule. */
export function banner(versions: readonly Version[], current: Version): Banner | undefined {
  const latest = versions.filter((version) => version.preferred === true);
  if (latest.length !== 1) return undefined;
  const [preferred] = latest as [Version];
  if (current.version === preferred.version) return undefined;
  const text =
    current.version === "dev"
      ? "This playground runs main, the development version: what it accepts may not be released yet."
      : `This playground runs an old version of Scenet, ${current.version}.`;
  return { text, latest: preferred };
}

/** Fetch switcher.json, or no versions when it cannot be had. */
export async function fetchVersions(): Promise<Version[]> {
  try {
    const response = await fetch(SWITCHER_URL);
    return response.ok ? parseVersions(await response.json()) : [];
  } catch {
    return [];
  }
}
