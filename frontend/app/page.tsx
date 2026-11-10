import { redirect } from "next/navigation";

// The app opens straight to the dashboard. If login has been turned on, the app shell sends signed-out visitors to /login.
export default function Home() { redirect("/dashboard"); }
