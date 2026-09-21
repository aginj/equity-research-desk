import type { DefaultSession } from "next-auth";

import type { Role } from "@/auth.config";

declare module "next-auth" {
  interface Session {
    /** Short-lived HS256 token for the research API (`Authorization: Bearer`). */
    apiToken?: string;
    /** Unix seconds when `apiToken` expires. */
    apiTokenExp?: number;
    user: {
      id: string;
      role: Role;
    } & DefaultSession["user"];
  }
}

// `next-auth/jwt` only re-exports from `@auth/core/jwt`; augment the defining module.
declare module "@auth/core/jwt" {
  interface JWT {
    role?: Role;
    apiToken?: string;
    apiTokenExp?: number;
  }
}
