"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Mail,
  MessageSquare,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";

const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 18 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-40px" },
  transition: { duration: 0.5, delay, ease: [0.25, 0.46, 0.45, 0.94] as const },
});

const metrics = [
  {
    label: "Active Coordinations",
    value: "27",
    detail: "+6 this week",
    icon: Activity,
  },
  {
    label: "Meetings Confirmed",
    value: "84",
    detail: "Last 30 days",
    icon: CheckCircle2,
  },
  {
    label: "Pending Approvals",
    value: "5",
    detail: "2 high priority",
    icon: ShieldCheck,
  },
  {
    label: "Avg Resolution Time",
    value: "3.8h",
    detail: "Thread start to booking",
    icon: Clock3,
  },
];

const meetingRows = [
  {
    title: "Product Roadmap Sync",
    owner: "ananya@team.com",
    participants: "5 participants",
    status: "Awaiting Approval",
    when: "Today, 5:30 PM",
  },
  {
    title: "US Client Onboarding",
    owner: "rishi@team.com",
    participants: "3 participants",
    status: "Coordinating",
    when: "Tomorrow, 9:00 PM",
  },
  {
    title: "Design QA Alignment",
    owner: "meera@team.com",
    participants: "4 participants",
    status: "Booked",
    when: "Tue, 6:00 PM",
  },
  {
    title: "Sales Strategy Review",
    owner: "arjun@team.com",
    participants: "6 participants",
    status: "Needs Clarification",
    when: "Wed, 4:00 PM",
  },
];

const approvalQueue = [
  {
    thread: "Product Roadmap Sync",
    reason: "Two equally ranked slots and VIP attendee conflict.",
    age: "12m ago",
  },
  {
    thread: "Sales Strategy Review",
    reason: "Ambiguous response: 'later this week should work'.",
    age: "31m ago",
  },
  {
    thread: "Hiring Panel Coordination",
    reason: "External attendee requested non-standard hours.",
    age: "1h ago",
  },
];

const calendarFeed = [
  {
    slot: "09:00-09:45",
    title: "Founders Weekly",
    owner: "Owner: dishant@team.com",
    tone: "bg-emerald-50 text-emerald-700 border-emerald-100",
  },
  {
    slot: "11:00-11:30",
    title: "Sprint Planning",
    owner: "Owner: rishi@team.com",
    tone: "bg-blue-50 text-blue-700 border-blue-100",
  },
  {
    slot: "14:00-15:00",
    title: "Client Onboarding",
    owner: "Owner: ananya@team.com",
    tone: "bg-amber-50 text-amber-700 border-amber-100",
  },
  {
    slot: "17:30-18:00",
    title: "Design QA Alignment",
    owner: "Owner: meera@team.com",
    tone: "bg-violet-50 text-violet-700 border-violet-100",
  },
];

const emailTimeline = [
  {
    type: "inbound",
    subject: "Re: Product Roadmap Sync",
    preview: "Thursday after lunch works for me, but not before 2 PM.",
    actor: "From: tara@client.com",
    time: "2m ago",
  },
  {
    type: "outbound",
    subject: "MailMind suggested two overlap windows",
    preview: "I found two suitable slots for everyone. Please confirm your preference.",
    actor: "By MailMind for ananya@team.com",
    time: "15m ago",
  },
  {
    type: "system",
    subject: "Approval requested from manager",
    preview: "Thread moved to approval queue due to ambiguity threshold.",
    actor: "System event",
    time: "19m ago",
  },
  {
    type: "outbound",
    subject: "Meeting Confirmation: Design QA Alignment",
    preview: "Your meeting is booked for Tuesday 6:00 PM IST. Calendar invites sent.",
    actor: "By MailMind for meera@team.com",
    time: "42m ago",
  },
];

function statusClasses(status: string) {
  if (status === "Booked") return "bg-emerald-50 text-emerald-700 border-emerald-100";
  if (status === "Awaiting Approval") return "bg-amber-50 text-amber-700 border-amber-100";
  if (status === "Needs Clarification") return "bg-rose-50 text-rose-700 border-rose-100";
  return "bg-blue-50 text-blue-700 border-blue-100";
}

function timelineDot(type: string) {
  if (type === "inbound") return "bg-blue-500";
  if (type === "outbound") return "bg-emerald-500";
  return "bg-amber-500";
}

export default function DashboardPage() {
  const router = useRouter();
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    const isAuthenticated = window.localStorage.getItem("mailmind_auth") === "true";
    if (!isAuthenticated) {
      router.replace("/login?next=/dashboard");
      return;
    }
    setAuthReady(true);
  }, [router]);

  if (!authReady) {
    return (
      <main className="relative min-h-screen overflow-hidden bg-background px-6 py-10 md:px-10 lg:px-14">
        <section className="mx-auto max-w-7xl">
          <div className="rounded-2xl border border-white/80 bg-[#f5f3ef] p-8 text-sm text-muted-foreground shadow-[0_8px_30px_rgba(0,0,0,0.06)]">
            Verifying your access...
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-background px-6 py-10 md:px-10 lg:px-14">
      <div className="pointer-events-none absolute left-[-180px] top-[-120px] h-[380px] w-[380px] rounded-full bg-accent/10 blur-[80px]" />
      <div className="pointer-events-none absolute bottom-[-180px] right-[-120px] h-[420px] w-[420px] rounded-full bg-[#e8f0dd] blur-[90px]" />

      <section className="relative mx-auto flex max-w-7xl flex-col gap-6">
        <motion.div
          {...fadeUp(0)}
          className="rounded-3xl border border-white/80 bg-[#f5f3ef] p-6 shadow-[0_10px_40px_rgba(0,0,0,0.08)] md:p-8"
        >
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/10 px-3 py-1 text-xs font-medium text-accent">
                <Sparkles className="h-3.5 w-3.5" />
                Centralized Admin Console
              </div>
              <h1
                className="mt-3 text-4xl leading-[0.95] tracking-tight text-foreground md:text-5xl"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Team Meetings, Calendar, and Email Intelligence
              </h1>
              <p className="mt-3 max-w-3xl text-sm text-muted-foreground md:text-base">
                Unified visibility for every user-managed thread: Google Calendar events, inbound participant responses,
                MailMind replies, and manager approval actions in one place.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm">Filter: This Week</Button>
              <Button variant="outline" size="sm">Team: All Users</Button>
              <Button size="sm" className="bg-accent hover:bg-accent/90">Open Approval Queue</Button>
            </div>
          </div>
        </motion.div>

        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map((item, idx) => {
            const Icon = item.icon;
            return (
              <motion.article
                key={item.label}
                {...fadeUp(0.05 + idx * 0.06)}
                className="rounded-2xl border border-white/80 bg-[#f5f3ef] p-5 shadow-[0_6px_26px_rgba(0,0,0,0.06)]"
              >
                <div className="flex items-start justify-between">
                  <p className="text-sm text-muted-foreground">{item.label}</p>
                  <Icon className="h-4 w-4 text-accent" />
                </div>
                <p className="mt-2 text-3xl font-semibold tracking-tight text-foreground">{item.value}</p>
                <p className="mt-1 text-xs text-muted-foreground">{item.detail}</p>
              </motion.article>
            );
          })}
        </section>

        <section className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
          <motion.article
            {...fadeUp(0.1)}
            className="overflow-hidden rounded-2xl border border-white/80 bg-[#f5f3ef] shadow-[0_8px_30px_rgba(0,0,0,0.06)]"
          >
            <div className="flex items-center justify-between border-b border-border/70 px-5 py-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">All User Meetings</h2>
                <p className="text-xs text-muted-foreground">Cross-user scheduling view for managers and admins</p>
              </div>
              <Button variant="outline" size="sm">View Full Board</Button>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border/60 text-xs text-muted-foreground">
                    <th className="px-5 py-3 font-medium">Meeting</th>
                    <th className="px-5 py-3 font-medium">Owner</th>
                    <th className="px-5 py-3 font-medium">Status</th>
                    <th className="px-5 py-3 font-medium">Next Slot</th>
                  </tr>
                </thead>
                <tbody>
                  {meetingRows.map((row) => (
                    <tr key={row.title} className="border-b border-border/40 last:border-0">
                      <td className="px-5 py-4">
                        <p className="font-medium text-foreground">{row.title}</p>
                        <p className="text-xs text-muted-foreground">{row.participants}</p>
                      </td>
                      <td className="px-5 py-4 text-xs text-muted-foreground">{row.owner}</td>
                      <td className="px-5 py-4">
                        <span className={`inline-flex rounded-full border px-2 py-1 text-xs font-medium ${statusClasses(row.status)}`}>
                          {row.status}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-xs text-muted-foreground">{row.when}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.article>

          <motion.article
            {...fadeUp(0.16)}
            className="rounded-2xl border border-white/80 bg-[#f5f3ef] p-5 shadow-[0_8px_30px_rgba(0,0,0,0.06)]"
          >
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-lg font-semibold text-foreground">Manager Approval Queue</h2>
                <p className="text-xs text-muted-foreground">Threads requiring human intervention</p>
              </div>
              <AlertTriangle className="h-4 w-4 text-amber-600" />
            </div>

            <div className="mt-4 space-y-3">
              {approvalQueue.map((item) => (
                <div key={item.thread} className="rounded-xl border border-border/70 bg-white/70 p-3">
                  <p className="text-sm font-medium text-foreground">{item.thread}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{item.reason}</p>
                  <div className="mt-2 flex items-center justify-between">
                    <span className="text-[11px] text-muted-foreground">{item.age}</span>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline">Reject</Button>
                      <Button size="sm" className="bg-accent hover:bg-accent/90">Approve</Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </motion.article>
        </section>

        <section className="grid gap-5 xl:grid-cols-2">
          <motion.article
            {...fadeUp(0.2)}
            className="rounded-2xl border border-white/80 bg-[#f5f3ef] p-5 shadow-[0_8px_30px_rgba(0,0,0,0.06)]"
          >
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-lg font-semibold text-foreground">Google Calendar (All Users)</h2>
                <p className="text-xs text-muted-foreground">Today&apos;s merged calendar view for connected accounts</p>
              </div>
              <CalendarDays className="h-4 w-4 text-accent" />
            </div>

            <div className="mt-4 space-y-2">
              {calendarFeed.map((event) => (
                <div
                  key={`${event.slot}-${event.title}`}
                  className={`flex items-center justify-between rounded-xl border px-3 py-2.5 ${event.tone}`}
                >
                  <div>
                    <p className="text-sm font-medium">{event.title}</p>
                    <p className="text-xs opacity-80">{event.owner}</p>
                  </div>
                  <p className="text-xs font-semibold">{event.slot}</p>
                </div>
              ))}
            </div>

            <div className="mt-4 flex items-center justify-between rounded-xl border border-border/70 bg-white/70 px-3 py-2.5 text-xs">
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <Users className="h-3.5 w-3.5" />
                11 connected users · 100% sync healthy
              </div>
              <Button size="sm" variant="outline">Open Full Calendar</Button>
            </div>
          </motion.article>

          <motion.article
            {...fadeUp(0.24)}
            className="rounded-2xl border border-white/80 bg-[#f5f3ef] p-5 shadow-[0_8px_30px_rgba(0,0,0,0.06)]"
          >
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-lg font-semibold text-foreground">Email and Agent Activity</h2>
                <p className="text-xs text-muted-foreground">Inbound emails, MailMind replies, and system actions</p>
              </div>
              <Mail className="h-4 w-4 text-accent" />
            </div>

            <div className="mt-4 space-y-3">
              {emailTimeline.map((item) => (
                <div key={`${item.subject}-${item.time}`} className="rounded-xl border border-border/70 bg-white/75 p-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={`h-2.5 w-2.5 rounded-full ${timelineDot(item.type)}`} />
                      <p className="text-sm font-medium text-foreground">{item.subject}</p>
                    </div>
                    <span className="text-[11px] text-muted-foreground">{item.time}</span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{item.preview}</p>
                  <div className="mt-2 inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">
                    <MessageSquare className="h-3 w-3" />
                    {item.actor}
                  </div>
                </div>
              ))}
            </div>
          </motion.article>
        </section>
      </section>
    </main>
  );
}
