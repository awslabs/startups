import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Fixture middleware: auth-gate the dashboard, rewrite legacy blog paths.
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/dashboard")) {
    const session = request.cookies.get("session");
    if (!session) {
      return NextResponse.redirect(new URL("/login", request.url));
    }
  }

  if (pathname.startsWith("/old-blog/")) {
    return NextResponse.rewrite(
      new URL(pathname.replace("/old-blog/", "/blog/"), request.url),
    );
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/old-blog/:path*"],
};
