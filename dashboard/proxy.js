import { NextResponse } from "next/server";

// The working paper's wrapper (public/paper/index.html) uses relative links,
// so it must be served at /paper/ with its trailing slash. With
// skipTrailingSlashRedirect (next.config.js) the path reaches here as
// requested: send the bare /paper to /paper/, and let the /paper/ rewrite
// serve the wrapper. The target is a plain URL because NextURL would strip
// the trailing slash again.
export function proxy(request) {
  const { basePath, pathname, search } = request.nextUrl;
  if (pathname === "/paper") {
    return NextResponse.redirect(new URL(`${basePath}/paper/${search}`, request.url), 308);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/paper"],
};
