import NextAuth from "next-auth";
import { NextResponse } from "next/server";

import { authConfig } from "@/auth.config";

// Edge-safe instance: decodes the session cookie only, no database.
const { auth } = NextAuth(authConfig);

export default auth((request) => {
  const { pathname, search } = request.nextUrl;
  const session = request.auth;
  // Mirror the API: with no JWT secret configured, desk admin is open locally.
  const authConfigured = Boolean(process.env.SMP_AUTH_JWT_SECRET);

  if (pathname.startsWith("/workspace") && !session?.user) {
    const url = new URL("/signin", request.url);
    url.searchParams.set("callbackUrl", pathname + search);
    return NextResponse.redirect(url);
  }

  if (pathname.startsWith("/admin")) {
    if (!authConfigured) {
      return NextResponse.next();
    }
    if (!session?.user) {
      const url = new URL("/signin", request.url);
      url.searchParams.set("callbackUrl", pathname + search);
      return NextResponse.redirect(url);
    }
    if (session.user.role !== "admin") {
      return NextResponse.redirect(new URL("/?denied=admin", request.url));
    }
  }

  return NextResponse.next();
});

export const config = {
  matcher: ["/workspace/:path*", "/admin/:path*"],
};
