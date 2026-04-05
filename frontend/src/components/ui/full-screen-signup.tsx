"use client";

import { ArrowRight, Sparkles, SunIcon as Sunburst } from "lucide-react";
import { signIn } from "next-auth/react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

export const FullScreenSignup = () => {
  const [nextPath, setNextPath] = useState("/dashboard");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailError, setEmailError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [googleEnabled, setGoogleEnabled] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedNext = params.get("next");
    const requestedGoogleState = params.get("google");

    if (requestedNext) {
      setNextPath(requestedNext);
    }

    if (requestedGoogleState === "off") {
      setGoogleEnabled(false);
    }
  }, []);

  const validateEmail = (value: string) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  };

  const validatePassword = (value: string) => {
    return value.length >= 8;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    let valid = true;

    if (!validateEmail(email)) {
      setEmailError("Please enter a valid email address.");
      valid = false;
    } else {
      setEmailError("");
    }

    if (!validatePassword(password)) {
      setPasswordError("Password must be at least 8 characters.");
      valid = false;
    } else {
      setPasswordError("");
    }

    setSubmitted(true);

    if (valid) {
      await signIn("credentials", {
        email,
        password,
        callbackUrl: nextPath,
      });
      setEmail("");
      setPassword("");
      setSubmitted(false);
    }
  };

  const handleGoogleSignIn = async () => {
    await signIn("google", { callbackUrl: nextPath });
  };

  return (
    <div className="relative min-h-screen overflow-hidden px-4 py-10 md:px-8">
      <div className="pointer-events-none absolute left-[-180px] top-[-120px] h-[380px] w-[380px] rounded-full bg-accent/10 blur-[80px]" />
      <div className="pointer-events-none absolute bottom-[-180px] right-[-120px] h-[420px] w-[420px] rounded-full bg-[#e8f0dd] blur-[90px]" />

      <div className="relative mx-auto flex w-full max-w-6xl overflow-hidden rounded-3xl border border-white/80 bg-[#f5f3ef] shadow-[0_20px_80px_rgba(0,0,0,0.10)] md:min-h-[700px] md:flex-row">
        <div className="relative min-h-[320px] w-full overflow-hidden md:min-h-0 md:w-1/2">
          <video
            className="absolute inset-0 h-full w-full object-cover"
            autoPlay
            loop
            muted
            playsInline
          >
            <source src="/login.mp4" type="video/mp4" />
          </video>
          <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/30 to-black/10" />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(99,102,241,0.28),transparent_45%)]" />

          <div className="relative z-10 flex h-full flex-col justify-start p-8 text-white md:p-10">
            <div className="inline-flex w-fit items-center gap-2 rounded-full border border-white/25 bg-white/10 px-3 py-1 text-xs">
              <Sparkles className="h-3.5 w-3.5" />
              MailMind Onboarding
            </div>

            <div className="mt-6">
              <h1
                className="max-w-md text-4xl leading-[0.95] tracking-tight md:text-5xl"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Build Meetings Faster, With Less Back-and-Forth
              </h1>
              <p className="mt-3 max-w-md text-sm text-white/85 md:text-base">
                Create your manager workspace and centralize team calendars, meeting threads,
                and MailMind-assisted email coordination.
              </p>
            </div>
          </div>
        </div>

        <div className="w-full bg-[#f5f3ef] p-8 text-foreground md:w-1/2 md:p-10">
          <div className="mb-7">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/10 px-3 py-1 text-xs font-medium text-accent">
              <Sunburst className="h-3.5 w-3.5" />
              Unified Auth
            </div>

            <h2 className="text-3xl font-medium tracking-tight">Welcome Back</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Log in to manage centralized scheduling operations.
            </p>
          </div>

          <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
            <div>
              <label htmlFor="email" className="mb-2 block text-sm text-muted-foreground">
                Work email
              </label>
              <input
                type="email"
                id="email"
                placeholder="manager@company.com"
                className={`h-10 w-full rounded-xl border bg-white px-3 text-sm text-foreground outline-none transition focus:border-accent ${
                  emailError ? "border-red-500" : "border-border"
                }`}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={!!emailError}
                aria-describedby="email-error"
              />
              {emailError && (
                <p id="email-error" className="mt-1 text-xs text-red-500">
                  {emailError}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="password" className="mb-2 block text-sm text-muted-foreground">
                Password
              </label>
              <input
                type="password"
                id="password"
                className={`h-10 w-full rounded-xl border bg-white px-3 text-sm text-foreground outline-none transition focus:border-accent ${
                  passwordError ? "border-red-500" : "border-border"
                }`}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={!!passwordError}
                aria-describedby="password-error"
              />
              {passwordError && (
                <p id="password-error" className="mt-1 text-xs text-red-500">
                  {passwordError}
                </p>
              )}
            </div>

            <Button type="submit" size="lg" className="mt-1 h-11 w-full bg-accent hover:bg-accent/90">
              Log In
              <ArrowRight className="ml-1.5 h-4 w-4" />
            </Button>

            <div className="relative py-1">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border/80" />
              </div>
              <div className="relative flex justify-center">
                <span className="bg-[#f5f3ef] px-2 text-xs text-muted-foreground">or continue with</span>
              </div>
            </div>

            {googleEnabled ? (
              <Button
                type="button"
                variant="outline"
                size="lg"
                className="h-11 w-full bg-white/90 hover:bg-white"
                onClick={handleGoogleSignIn}
              >
                <Sunburst className="mr-1.5 h-4 w-4" />
                Sign in with Google
              </Button>
            ) : null}

            {submitted && emailError === "" && passwordError === "" ? (
              <p className="text-center text-xs text-muted-foreground">Submitting...</p>
            ) : null}

            <div className="text-center text-xs text-muted-foreground">
              By continuing, you agree to secure workspace access policies.
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
