import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

const API = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const authOptions: NextAuthOptions = {
  session: { strategy: "jwt", maxAge: 60 * 60 * 12 },       // matches the API token lifetime
  pages: { signIn: "/login" },
  providers: [
    CredentialsProvider({
      name: "Email and password",
      credentials: { email: { label: "Email", type: "email" }, password: { label: "Password", type: "password" } },
      async authorize(creds) {
        if (!creds?.email || !creds?.password) return null;
        const res = await fetch(`${API}/api/accounts/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: creds.email, password: creds.password }) });
        if (!res.ok) return null;
        const d = await res.json();
        return { id: String(d.user.id), name: d.user.name, email: d.user.email, role: d.user.role, accessToken: d.token };
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) { token.accessToken = user.accessToken; token.role = user.role; token.uid = user.id; }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken; session.role = token.role; session.user.id = token.uid;
      return session;
    },
  },
};
