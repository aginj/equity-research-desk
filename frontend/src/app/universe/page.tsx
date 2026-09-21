import { redirect } from "next/navigation";

/** The universe editor moved under /admin (admin-only). Keep old links working. */
export default function UniverseRedirect() {
  redirect("/admin");
}
