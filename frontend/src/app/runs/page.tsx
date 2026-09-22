import { redirect } from "next/navigation";

export default function RunsRedirect() {
  redirect("/admin?tab=runs");
}
