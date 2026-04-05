"use client";

import { motion } from "framer-motion";
import {
  Play,
  Mail,
  Calendar,
  Shield,
  Users,
  Zap,
  MessageSquare,
  Clock,
  ArrowRight,
  ChevronDown,
  Check,
  Sparkles,
  Globe,
  Bot,
  Send,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Navbar } from "@/components/ui/navbar";
import { Footer } from "@/components/ui/footer";
import { DashboardPreview } from "@/components/dashboard-preview";
import { 
  SlackLogo, 
  GmailLogo, 
  GoogleMeetLogo, 
  GoogleCalendarLogo 
} from "@/components/ui/app-logos";
import { LogoCloud } from "@/components/ui/logo-cloud-3";
import { EtheralShadow } from "@/components/ui/etheral-shadow";
import { useState } from "react";

/* ─── Animation helpers ─── */
const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 20 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-50px" },
  transition: { duration: 0.6, delay, ease: [0.25, 0.46, 0.45, 0.94] as const },
});

const fadeIn = (delay = 0) => ({
  initial: { opacity: 0 },
  whileInView: { opacity: 1 },
  viewport: { once: true, margin: "-50px" },
  transition: { duration: 0.5, delay },
});

/* ─── Shared Section Wrapper ─── */
function Section({
  children,
  className = "",
  innerClassName = "max-w-6xl",
  id,
}: {
  children: React.ReactNode;
  className?: string;
  innerClassName?: string;
  id?: string;
}) {
  return (
    <section id={id} className={`px-6 md:px-12 lg:px-20 ${className}`}>
      <div className={`mx-auto ${innerClassName}`}>{children}</div>
    </section>
  );
}

/* ─── Feature Card (trydot-style full-width) ─── */
function FeatureCard({
  badge,
  badgeIcon: BadgeIcon,
  heading,
  description,
  children,
  delay = 0,
  withBackground = false,
}: {
  badge: string;
  badgeIcon: React.ElementType;
  heading: string;
  description: string;
  children: React.ReactNode;
  delay?: number;
  withBackground?: boolean;
}) {
  return (
    <motion.div
      {...fadeUp(delay)}
      whileHover={{ y: -8, transition: { duration: 0.25, ease: "easeOut" } }}
      className="relative rounded-2xl bg-[#f5f3ef] p-8 md:p-10 flex flex-col gap-5 border border-white/80 shadow-[0_2px_12px_rgba(0,0,0,0.06),_0_1px_3px_rgba(0,0,0,0.03)] hover:shadow-[0_24px_64px_rgba(0,0,0,0.11),_0_6px_20px_rgba(0,0,0,0.07)] transition-shadow duration-300 cursor-default overflow-hidden"
    >
      {withBackground && (
        <div className="absolute inset-0 z-0 opacity-100">
          <EtheralShadow 
            className="[&_h1]:hidden"
            animation={{ scale: 100, speed: 90 }} 
            noise={{ opacity: 1, scale: 1.2 }} 
            sizing="fill"
          />
        </div>
      )}
      
      {/* Content wrapper to stay above background */}
      <div className="relative z-10 flex flex-col gap-5 h-full">
      {/* Badge / Label */}
      <div className="inline-flex items-center gap-2 text-sm text-muted-foreground">
        <BadgeIcon className="h-4 w-4" />
        <span>{badge}</span>
      </div>
      {/* Heading */}
      <h3
        className="text-2xl md:text-3xl lg:text-4xl leading-[0.95] tracking-tight text-foreground"
        style={{ fontFamily: "var(--font-display)" }}
      >
        {heading}
      </h3>
      {/* Description */}
      <p className="text-base text-muted-foreground leading-relaxed">
        {description}
      </p>
      {/* Visual */}
      <div className="mt-3">{children}</div>
      </div>
    </motion.div>
  );
}

/* ─── Bento Grid Card ─── */
function BentoCard({
  title,
  description,
  children,
  className = "",
  delay = 0,
}: {
  title: string;
  description: string;
  children?: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      {...fadeUp(delay)}
      whileHover={{ y: -5, transition: { duration: 0.2, ease: "easeOut" } }}
      className={`rounded-xl bg-[#f5f3ef] p-6 md:p-7 border border-white/70 shadow-[0_1px_6px_rgba(0,0,0,0.05),_0_1px_2px_rgba(0,0,0,0.03)] hover:shadow-[0_12px_32px_rgba(0,0,0,0.10),_0_4px_10px_rgba(0,0,0,0.05)] transition-shadow duration-300 cursor-default ${className}`}
    >
      <h4 className="text-base md:text-lg font-semibold text-foreground mb-1.5">{title}</h4>
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        {description}
      </p>
      {children}
    </motion.div>
  );
}

/* ─── FAQ Item ─── */
function FAQItem({
  question,
  answer,
  delay = 0,
}: {
  question: string;
  answer: string;
  delay?: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <motion.div
      {...fadeUp(delay)}
      className="border-b border-border"
    >
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full py-5 text-left"
      >
        <span className="text-base md:text-lg font-medium text-foreground pr-4">
          {question}
        </span>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground shrink-0 transition-transform duration-300 ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>
      <div
        className={`overflow-hidden transition-all duration-300 ${
          open ? "max-h-40 pb-5" : "max-h-0"
        }`}
      >
        <p className="text-base text-muted-foreground leading-relaxed">
          {answer}
        </p>
      </div>
    </motion.div>
  );
}

/* ═════════════════════════════════════════
   MAIN PAGE
   ═════════════════════════════════════════ */
export default function Home() {
  return (
    <div className="min-h-screen flex flex-col bg-background overflow-x-hidden">
      {/* ─────────────────── Navbar ─────────────────── */}
      <Navbar />

      {/* ─────────────────── Hero ─────────────────── */}
      <section className="relative flex flex-col items-center justify-start pt-24 md:pt-28 pb-16 md:pb-24">
        {/* Background Video Wrapper */}
        <div className="absolute inset-0 overflow-hidden z-0 pointer-events-none">
          <video
            autoPlay
            loop
            muted
            playsInline
            className="absolute inset-0 w-full h-full object-cover"
          >
            <source
              src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260319_015952_e1deeb12-8fb7-4071-a42a-60779fc64ab6.mp4"
              type="video/mp4"
            />
          </video>
  
          {/* Bottom fade gradient — softens the hero-to-content edge */}
          <div className="absolute bottom-0 left-0 right-0 h-[28rem] bg-gradient-to-t from-background via-background/90 via-50% to-transparent" />
        </div>

        {/* Content Layer */}
        <div className="relative z-10 flex flex-col items-center w-full px-6">
          {/* Badge */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/5 px-5 py-2 text-sm text-accent font-medium font-sans mb-6"
          >
            Your Gmail, supercharged ✨
          </motion.div>

          {/* Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1, ease: [0.25, 0.46, 0.45, 0.94] as const }}
            className="text-center text-5xl md:text-6xl lg:text-[5rem] leading-[0.95] tracking-tight text-foreground max-w-xl"
            style={{ fontFamily: "var(--font-display)" }}
          >
            The Future of{" "}
            <em
              className="not-italic"
              style={{
                fontFamily: "var(--font-display)",
                fontStyle: "italic",
              }}
            >
              Smarter
            </em>{" "}
            Email Coordination
          </motion.h1>

          {/* Subheadline */}
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2, ease: [0.25, 0.46, 0.45, 0.94] as const }}
            className="mt-4 text-center text-base md:text-lg text-muted-foreground max-w-[650px] leading-relaxed font-sans"
          >
            Automate meeting scheduling with intelligent AI agents that read
            emails, resolve conflicts, and book calendar events—so your team can
            focus on what matters most.
          </motion.p>

          {/* CTA Buttons */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3, ease: [0.25, 0.46, 0.45, 0.94] as const }}
            className="mt-5 flex items-center gap-3"
          >
            <Button className="rounded-full px-6 py-5 text-sm font-medium font-sans">
              Book a demo
            </Button>

            <Button
              variant="ghost"
              size="icon"
              className="h-11 w-11 rounded-full border-0 bg-background shadow-[0_2px_12px_rgba(0,0,0,0.08)] hover:bg-background/80"
            >
              <Play className="h-4 w-4 fill-foreground" />
            </Button>
          </motion.div>

          {/* Dashboard Preview */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.8,
              delay: 0.5,
              ease: [0.25, 0.46, 0.45, 0.94],
            }}
            className="mt-8 w-full max-w-5xl"
          >
            <div
              className="rounded-2xl overflow-hidden p-3 md:p-4"
              style={{
                background: "rgba(255, 255, 255, 0.4)",
                border: "1px solid rgba(255, 255, 255, 0.5)",
                boxShadow: "var(--shadow-dashboard)",
              }}
            >
              <DashboardPreview />
            </div>
          </motion.div>
        </div>
      </section>

      {/* ─────────────────── Trusted By / Integrations ─────────────────── */}
      <Section className="pt-10 pb-16 md:pt-14 md:pb-20">
        <motion.div {...fadeIn(0.1)} className="text-center">
          <p className="text-sm uppercase tracking-[0.2em] text-muted-foreground mb-12 font-medium">
            Powering workflow with native integrations
          </p>
          <LogoCloud 
            className="mt-8"
            logos={[
              { src: "/images/gmail-logo-1.svg", alt: "Gmail" },
              { src: "/images/Google-Calendar-Logo-SVG_007.svg", alt: "Calendar" },
              { src: "/images/Google-Meet-Logo-SVG_014.svg", alt: "Meet" },
              { src: "/images/Slack-Logo-4.svg", alt: "Slack" },
              // Duplicate once to ensure smooth infinite scroll if screen is wide
              { src: "/images/gmail-logo-1.svg", alt: "Gmail 2" },
              { src: "/images/Google-Calendar-Logo-SVG_007.svg", alt: "Calendar 2" },
              { src: "/images/Google-Meet-Logo-SVG_014.svg", alt: "Meet 2" },
              { src: "/images/Slack-Logo-4.svg", alt: "Slack 2" },
            ]} 
          />


        </motion.div>
      </Section>

      {/* ─────────────────── Features Grid ─────────────────── */}
      <Section className="py-6" id="features" innerClassName="max-w-[1400px]">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FeatureCard
          badge="AI-Powered Coordination"
          badgeIcon={Sparkles}
          heading="Smart scheduling. Zero back-and-forth."
          description="Just describe your meeting in natural language — MailMind orchestrates the entire coordination via email, from availability requests to final confirmation."
          withBackground={true}
        >
          {/* Email Compose Mockup */}
          <div className="rounded-xl border border-border bg-[#f5f3ef] p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-3 pb-3 border-b border-border">
              <div className="h-7 w-7 rounded-full bg-accent/10 flex items-center justify-center">
                <MessageSquare className="h-3.5 w-3.5 text-accent" />
              </div>
              <span className="text-xs font-medium text-foreground">
                MailMind Chat
              </span>
            </div>
            <div className="space-y-3">
              <div className="flex gap-3">
                <div className="h-6 w-6 rounded-full bg-secondary flex items-center justify-center shrink-0">
                  <span className="text-[9px] font-bold text-foreground">
                    DG
                  </span>
                </div>
                <div className="rounded-xl rounded-tl-sm bg-secondary px-3 py-2 text-xs text-foreground max-w-[85%]">
                  Schedule a 1-hour design review with Ravi, Chen, and Sarah
                  this week. Keep it professional.
                </div>
              </div>
              <div className="flex gap-3 justify-end">
                <div className="rounded-xl rounded-tr-sm bg-accent/10 px-3 py-2 text-xs text-foreground max-w-[85%]">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Sparkles className="h-3 w-3 text-accent" />
                    <span className="text-[10px] font-medium text-accent">
                      MailMind
                    </span>
                  </div>
                  Got it! I&apos;ll coordinate a 1-hour design review with 3
                  participants. Here&apos;s my plan:
                  <div className="mt-2 space-y-1 text-[10px] text-muted-foreground">
                    <div className="flex items-center gap-1.5">
                      <Check className="h-3 w-3 text-emerald-500" />
                      Participants: Ravi, Chen, Sarah
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Check className="h-3 w-3 text-emerald-500" />
                      Duration: 1 hour
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Check className="h-3 w-3 text-emerald-500" />
                      Tone: Professional
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Clock className="h-3 w-3 text-amber-500" />
                      Sending availability requests...
                    </div>
                  </div>
                </div>
                <div className="h-6 w-6 rounded-full bg-accent flex items-center justify-center shrink-0">
                  <Bot className="h-3 w-3 text-accent-foreground" />
                </div>
              </div>
            </div>
          </div>
        </FeatureCard>

        <FeatureCard
          badge="Human-in-the-Loop"
          badgeIcon={Shield}
          heading="Full control. Total transparency."
          description="Every outbound email passes through your approval queue. Review, edit, or reject — MailMind never sends without your explicit approval."
          delay={0.1}
          withBackground={true}
        >
          {/* Approval Queue Mockup */}
          <div className="rounded-xl border border-border bg-[#f5f3ef] p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3 pb-3 border-b border-border">
              <div className="flex items-center gap-2">
                <Shield className="h-3.5 w-3.5 text-accent" />
                <span className="text-xs font-medium text-foreground">
                  Approval Queue
                </span>
              </div>
              <span className="text-[10px] text-amber-600 bg-amber-50 rounded-full px-2 py-0.5 font-medium">
                2 pending
              </span>
            </div>

            <div className="space-y-2.5">
              {[
                {
                  to: "ravi.patel@company.com",
                  subject: "Availability Request",
                  preview:
                    "Hi Ravi, I'd like to schedule a design review this week...",
                  time: "2m ago",
                },
                {
                  to: "chen.wei@company.com",
                  subject: "Meeting Confirmation",
                  preview:
                    "Meeting confirmed: Thursday 2:00 PM — 3:00 PM IST...",
                  time: "5m ago",
                },
              ].map((item, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-border p-3 hover:border-accent/30 transition-colors"
                >
                  <div className="flex items-start justify-between mb-1.5">
                    <div>
                      <span className="text-[10px] font-medium text-foreground">
                        {item.subject}
                      </span>
                      <span className="text-[9px] text-muted-foreground ml-2">
                        → {item.to}
                      </span>
                    </div>
                    <span className="text-[9px] text-muted-foreground">
                      {item.time}
                    </span>
                  </div>
                  <p className="text-[10px] text-muted-foreground mb-2 truncate">
                    {item.preview}
                  </p>
                  <div className="flex items-center gap-1.5">
                    <span className="rounded-md bg-emerald-500 px-2.5 py-1 text-[9px] font-medium text-white cursor-pointer">
                      Approve
                    </span>
                    <span className="rounded-md border border-border px-2.5 py-1 text-[9px] font-medium text-foreground cursor-pointer">
                      Edit
                    </span>
                    <span className="rounded-md border border-border px-2.5 py-1 text-[9px] font-medium text-red-500 cursor-pointer">
                      Reject
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </FeatureCard>
        </div>
      </Section>

      {/* ─────────────────── Bento Grid: Capabilities ─────────────────── */}
      <Section className="py-12 md:py-16" innerClassName="max-w-[1400px]">
        <motion.div {...fadeUp(0)} className="mb-10">
          <p className="text-sm text-accent font-semibold mb-2 tracking-wide uppercase">Capabilities</p>
          <h2
            className="text-3xl md:text-4xl lg:text-5xl leading-[0.95] tracking-tight text-foreground"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Everything you need to coordinate
          </h2>
          <p className="text-base md:text-lg text-muted-foreground mt-3">
            Your calendar, fully in your hands
          </p>
        </motion.div>

        {/* Row 1 — 2 cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <BentoCard
            title="Natural language requests"
            description="Just type — MailMind parses participants, duration, tone, and constraints"
            delay={0.05}
          >
            <div className="rounded-lg bg-secondary/50 p-4">
              <div className="flex items-center gap-2.5 text-sm text-foreground">
                <span className="font-medium">Team sync</span>
                <span className="text-accent">every Monday</span>
                <span className="text-accent">10am</span>
                <span className="text-muted-foreground">for</span>
                <span className="text-accent">1 hour</span>
              </div>
              <div className="flex items-center gap-2.5 mt-3">
                {["↑ title", "↑ recurrence", "↑ time", "↑ duration"].map(
                  (tag) => (
                    <span
                      key={tag}
                      className="text-xs text-accent/70 bg-accent/5 rounded-full px-2 py-0.5"
                    >
                      {tag}
                    </span>
                  )
                )}
              </div>
            </div>
          </BentoCard>

          <BentoCard
            title="Smart reply parsing"
            description="AI understands 'I'm free Tuesday 3pm' or 'anytime after lunch works'"
            delay={0.1}
          >
            <div className="space-y-3">
              {[
                {
                  name: "Ravi",
                  reply: '"Tuesday 3pm works for me"',
                  slot: "Tue 3:00 PM",
                },
                {
                  name: "Chen",
                  reply: '"Free after 2pm on Tues/Wed"',
                  slot: "Tue 3:00 PM, Wed 2:00 PM",
                },
              ].map((item) => (
                <div
                  key={item.name}
                  className="flex items-center gap-3 text-sm"
                >
                  <span className="font-medium text-foreground w-12">
                    {item.name}
                  </span>
                  <span className="text-muted-foreground flex-1 truncate">
                    {item.reply}
                  </span>
                  <ArrowRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                  <span className="text-accent font-medium whitespace-nowrap">
                    {item.slot}
                  </span>
                </div>
              ))}
            </div>
          </BentoCard>
        </div>

        {/* Row 2 — 2 cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <BentoCard
            title="Calendar integration"
            description="Connects with your workspace apps for real-time freebusy availability and instant scheduling."
            delay={0.15}
          >
            <div className="rounded-lg bg-secondary/50 p-4 mb-4">
              <div className="space-y-2">
                {["9:00 AM", "10:00 AM", "11:00 AM", "12:00 PM"].map(
                  (time, i) => (
                    <div key={time} className="flex items-center gap-3 text-sm">
                      <span className="w-18 text-muted-foreground text-xs">{time}</span>
                      {i === 1 ? (
                        <div className="flex-1 rounded bg-accent/15 text-accent px-3 py-1.5 text-xs font-medium">
                          Team Standup (busy)
                        </div>
                      ) : i === 2 ? (
                        <div className="flex-1 rounded bg-emerald-50 text-emerald-600 px-3 py-1.5 text-xs font-medium">
                          ✓ Available — optimal slot
                        </div>
                      ) : (
                        <div className="flex-1 rounded bg-secondary/80 px-3 py-1.5 text-xs text-muted-foreground">
                          Available
                        </div>
                      )}
                    </div>
                  )
                )}
              </div>
            </div>
            
            <div className="flex items-center justify-between pt-3 border-t border-border/30">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Active Connections</span>
              <div className="flex items-center gap-3">
                <GmailLogo className="h-4 w-4 grayscale hover:grayscale-0 transition-all cursor-help" title="Gmail Connected" />
                <GoogleCalendarLogo className="h-4 w-4 grayscale hover:grayscale-0 transition-all cursor-help" title="Calendar Connected" />
                <GoogleMeetLogo className="h-4 w-4 grayscale hover:grayscale-0 transition-all cursor-help" title="Meet Connected" />
                <SlackLogo className="h-4 w-4 grayscale hover:grayscale-0 transition-all cursor-help" title="Slack Connected" />
              </div>
            </div>
          </BentoCard>

          <BentoCard
            title="Multi-party coordination"
            description="Handles N-party scheduling with automatic overlap detection across timezones"
            delay={0.2}
          >
            <div className="flex items-center gap-4">
              <div className="flex -space-x-2">
                {["R", "C", "S", "M"].map((initial, i) => (
                  <div
                    key={initial}
                    className="h-8 w-8 rounded-full border-2 border-background flex items-center justify-center text-[10px] font-bold text-white"
                    style={{
                      backgroundColor: [
                        "hsl(239 84% 67%)",
                        "hsl(160 60% 45%)",
                        "hsl(25 95% 53%)",
                        "hsl(340 82% 52%)",
                      ][i],
                    }}
                  >
                    {initial}
                  </div>
                ))}
              </div>
              <div className="text-sm">
                <span className="font-medium text-foreground">
                  4 participants
                </span>
                <span className="text-muted-foreground"> across </span>
                <span className="font-medium text-foreground">3 timezones</span>
              </div>
            </div>
          </BentoCard>
        </div>

        {/* Row 3 — 4 small cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            {
              icon: Mail,
              title: "Your identity",
              desc: "Emails sent from YOUR address",
            },
            {
              icon: Shield,
              title: "AI disclosure",
              desc: "Mandatory transparency block",
            },
            {
              icon: Calendar,
              title: "Auto-create events",
              desc: "Google Calendar + Meet link",
              logos: [GoogleCalendarLogo, GoogleMeetLogo]
            },
            {
              icon: Zap,
              title: "Instant reminders",
              desc: "In-platform notifications + Slack",
              logos: [SlackLogo]
            },
          ].map((item, i) => (
            <motion.div
              key={item.title}
              {...fadeUp(0.05 * i)}
              whileHover={{ y: -4, transition: { duration: 0.2, ease: "easeOut" } }}
              className="rounded-xl bg-[#f5f3ef] p-5 md:p-6 border border-white/70 shadow-[0_1px_5px_rgba(0,0,0,0.05)] hover:shadow-[0_10px_28px_rgba(0,0,0,0.09)] transition-shadow duration-300 cursor-default flex flex-col h-full"
            >
              <div className="flex justify-between items-start mb-3">
                <item.icon className="h-5 w-5 text-accent" />
                <div className="flex gap-1.5">
                  {item.logos?.map((Logo, idx) => (
                    <Logo key={idx} className="h-3.5 w-3.5 opacity-60" />
                  ))}
                </div>
              </div>
              <h4 className="text-sm md:text-base font-semibold text-foreground mb-1">
                {item.title}
              </h4>
              <p className="text-xs md:text-sm text-muted-foreground leading-relaxed flex-1">{item.desc}</p>
            </motion.div>
          ))}
        </div>
      </Section>

      {/* ─────────────────── How It Works ─────────────────── */}
      <Section className="py-16 md:py-24 bg-[#f5f3ef] rounded-3xl mx-4 md:mx-8 lg:mx-16" id="how-it-works">
        <motion.div {...fadeUp(0)} className="text-center mb-12">
          <h2
            className="text-3xl md:text-4xl lg:text-5xl leading-[0.95] tracking-tight text-foreground"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Three steps. That&apos;s it.
          </h2>
          <p className="text-base text-muted-foreground mt-3 max-w-lg mx-auto">
            From request to calendar invite — fully autonomous, always under
            your control.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            {
              step: "01",
              icon: MessageSquare,
              title: "Describe your meeting",
              description:
                "Type a natural language request in the MailMind chat. Specify participants, duration, and tone — or let MailMind infer it all.",
            },
            {
              step: "02",
              icon: Send,
              title: "MailMind coordinates",
              description:
                "AI agents email participants from your address, parse replies, extract time slots, and compute the optimal overlap automatically.",
            },
            {
              step: "03",
              icon: Calendar,
              title: "Meeting booked",
              description:
                "A Google Calendar event is created with a Meet link. All participants get an invite. You get a summary in-platform.",
            },
          ].map((item, i) => (
            <motion.div
              key={item.step}
              {...fadeUp(0.1 * i)}
              whileHover={{ y: -6, transition: { duration: 0.22, ease: "easeOut" } }}
              className="relative rounded-xl bg-white/80 p-6 border border-white/90 shadow-[0_2px_10px_rgba(0,0,0,0.06),_0_1px_3px_rgba(0,0,0,0.04)] hover:shadow-[0_14px_40px_rgba(0,0,0,0.10),_0_4px_12px_rgba(0,0,0,0.06)] transition-shadow duration-300 cursor-default"
            >
              <span className="text-4xl font-semibold text-border/80 absolute top-4 right-5">
                {item.step}
              </span>
              <div className="h-10 w-10 rounded-xl bg-accent/10 flex items-center justify-center mb-4">
                <item.icon className="h-5 w-5 text-accent" />
              </div>
              <h3
                className="text-xl md:text-2xl leading-[0.95] tracking-tight text-foreground mb-3"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {item.title}
              </h3>
              <p className="text-sm md:text-base text-muted-foreground leading-relaxed">
                {item.description}
              </p>
            </motion.div>
          ))}
        </div>
      </Section>

      {/* ─────────────────── Comparison Section (trydot-style strikethrough) ─────────────────── */}
      <Section className="py-16 md:py-24">
        <motion.h2
          {...fadeUp(0)}
          className="text-center text-4xl md:text-6xl lg:text-[4.5rem] leading-[0.95] tracking-tight text-foreground mb-16"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Stop coordinating.{" "}
          <span className="text-foreground">Start collaborating.</span>
        </motion.h2>

        <div className="max-w-4xl mx-auto space-y-12">
          {[
            {
              old: "27 back-and-forth emails",
              new: "One natural language request",
            },
            {
              old: "4 days to confirm a meeting",
              new: "Resolved in hours, not days",
            },
            {
              old: "Checking 5 calendars manually",
              new: "AI finds the overlap automatically",
            },
            {
              old: "Copy-pasting Zoom links",
              new: "Meet links added instantly",
            },
            {
              old: "Forgetting to follow up",
              new: "Automatic reminders & escalation",
            },
          ].map((item, i) => (
            <motion.div
              key={i}
              {...fadeUp(0.05 * i)}
              whileHover={{ scale: 1.02, x: 5, transition: { duration: 0.2, ease: "easeOut" } }}
              className="group flex items-center gap-6 md:gap-14 cursor-default"
            >
              <span
                className="flex-1 text-right text-lg md:text-xl lg:text-2xl text-muted-foreground/50 line-through decoration-1 transition-colors duration-300 group-hover:text-muted-foreground/30"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {item.old}
              </span>
              <ArrowRight className="h-6 w-6 md:h-8 md:w-8 text-accent shrink-0 transition-transform duration-300 group-hover:translate-x-2 group-hover:scale-110" />
              <span
                className="flex-1 text-lg md:text-xl lg:text-2xl font-medium text-foreground transition-colors duration-300 group-hover:text-accent"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {item.new}
              </span>
            </motion.div>
          ))}
        </div>
      </Section>

      {/* ─────────────────── FAQ ─────────────────── */}
      <Section className="py-14 md:py-20" id="faq">
        <motion.div {...fadeUp(0)} className="text-center mb-12">
          <h2
            className="text-3xl md:text-4xl lg:text-5xl leading-[0.95] tracking-tight text-foreground"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Frequently asked questions
          </h2>
          <p className="text-base md:text-lg text-muted-foreground mt-3 max-w-lg mx-auto">
            Everything you need to know about MailMind
          </p>
        </motion.div>

        <div className="max-w-2xl mx-auto">
          <FAQItem
            question="Does MailMind send emails as a bot?"
            answer="No. Every email is sent from YOUR email address via OAuth-authenticated Gmail API. Participants see emails from you — not from a bot or third-party address. A mandatory AI disclosure is appended for transparency."
            delay={0.05}
          />
          <FAQItem
            question="Can MailMind access my entire inbox?"
            answer="No. MailMind's Gmail OAuth scope is limited to read and send access only on the monitored inbox. It cannot delete, archive, label, or access anything outside the scope of coordination."
            delay={0.1}
          />
          <FAQItem
            question="Do participants need to sign up for MailMind?"
            answer="No. Email-only participants simply reply to a normal email. If they join MailMind, their connected Google Calendar enables automatic freebusy availability — making scheduling even faster."
            delay={0.15}
          />
          <FAQItem
            question="What happens if I don't approve an email?"
            answer="MailMind uses a tiered escalation: pending attention after 3 minutes, prominent flag after 2 hours, and expiry after 24 hours. No email is ever sent without explicit operator approval."
            delay={0.2}
          />
          <FAQItem
            question="How does MailMind handle timezone differences?"
            answer="MailMind normalizes all time expressions to a common timezone using deterministic logic. Participants can reply in their local timezone — the AI handles the conversion automatically."
            delay={0.25}
          />
          <FAQItem
            question="Is MailMind free to use?"
            answer="MailMind runs on free-tier APIs during development with minimal model cost. Pricing details for the production platform will be available at launch."
            delay={0.3}
          />
        </div>
      </Section>

      {/* ─────────────────── Final CTA ─────────────────── */}
      <Section className="py-16 md:py-24">
        <motion.div {...fadeUp(0)} className="text-center">
          <h2
            className="text-4xl md:text-5xl lg:text-6xl leading-[0.95] tracking-tight text-foreground mb-4"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Ready to stop{" "}
            <em
              style={{
                fontFamily: "var(--font-display)",
                fontStyle: "italic",
              }}
            >
              scheduling?
            </em>
          </h2>
          <p className="text-base md:text-lg text-muted-foreground max-w-lg mx-auto mb-8">
            Join the waitlist and be the first to experience autonomous email
            coordination.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Button className="rounded-full px-8 py-5 text-sm font-medium">
              Join the waitlist
            </Button>
            <Button
              variant="outline"
              className="rounded-full px-8 py-5 text-sm font-medium"
            >
              Book a demo
            </Button>
          </div>
        </motion.div>
      </Section>

      {/* ─────────────────── Footer ─────────────────── */}
      <Footer />
    </div>
  );
}
