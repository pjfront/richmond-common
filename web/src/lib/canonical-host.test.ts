import { describe, expect, it } from "vitest";

import nextConfig from "../../next.config";

describe("production host canonicalization", () => {
  it("permanently redirects every www path to the apex before route redirects", async () => {
    expect(nextConfig.redirects).toBeDefined();

    const redirects = await nextConfig.redirects!();

    expect(redirects[0]).toEqual({
      source: "/:path*",
      has: [{ type: "host", value: "www.richmondcommons.org" }],
      destination: "https://richmondcommons.org/:path*",
      permanent: true,
    });
  });
});
