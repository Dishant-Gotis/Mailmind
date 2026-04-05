"use client";

import React from "react";
import { motion } from "framer-motion";
import {
  Mail,
  ArrowRight,
} from "lucide-react";
import { Button } from "./button";

const LinkedinIcon = () => (
  <svg
    viewBox="0 0 24 24"
    aria-hidden="true"
    className="h-5 w-5 fill-current"
  >
    <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z" />
  </svg>
);

const InstagramIcon = () => (
  <svg
    viewBox="0 0 24 24"
    aria-hidden="true"
    className="h-5 w-5 fill-none stroke-current stroke-2"
  >
    <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
    <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
    <line x1="17.5" y1="6.5" x2="17.51" y2="6.5" />
  </svg>
);

const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 20 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-50px" },
  transition: { duration: 0.6, delay, ease: [0.25, 0.46, 0.45, 0.94] as const },
});

const XIcon = () => (
  <svg
    viewBox="0 0 24 24"
    aria-hidden="true"
    className="h-5 w-5 fill-current"
  >
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"></path>
  </svg>
);

const FooterLink = ({ href, children }: { href: string; children: React.ReactNode }) => (
  <li>
    <a
      href={href}
      className="text-sm text-muted-foreground hover:text-foreground transition-colors duration-200"
    >
      {children}
    </a>
  </li>
);

export function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="relative w-full bg-background pt-24 pb-12 px-6 md:px-12 lg:px-20 overflow-hidden">
      <div className="mx-auto max-w-7xl">
        {/* Top Section: Logo & Newsletter */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-10 mb-16">
          <motion.div {...fadeUp(0)} className="flex items-center gap-3 group cursor-default">
            <div className="relative w-8 h-8 flex items-center justify-center">
              <span className="absolute w-1.5 h-1.5 rounded-full bg-accent top-0 left-1/2 transform -translate-x-1/2 group-hover:scale-125 transition-transform"></span>
              <span className="absolute w-1.5 h-1.5 rounded-full bg-accent left-0 top-1/2 transform -translate-y-1/2 group-hover:scale-125 transition-transform"></span>
              <span className="absolute w-1.5 h-1.5 rounded-full bg-accent right-0 top-1/2 transform -translate-y-1/2 group-hover:scale-125 transition-transform"></span>
              <span className="absolute w-1.5 h-1.5 rounded-full bg-accent bottom-0 left-1/2 transform -translate-x-1/2 group-hover:scale-125 transition-transform"></span>
            </div>
            <span
              className="text-2xl md:text-3xl font-semibold tracking-tight text-foreground"
              style={{ fontFamily: "var(--font-display)" }}
            >
              MailMind
            </span>
          </motion.div>

          <motion.div {...fadeUp(0.1)} className="w-full md:w-auto max-w-md">
            <h4 className="text-sm font-medium text-foreground mb-4">Sign up to our newsletter</h4>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type="email"
                  placeholder="Email"
                  className="w-full h-10 bg-transparent border-b border-border/60 focus:border-foreground outline-none transition-colors text-sm px-1 py-2"
                />
              </div>
              <Button size="sm" className="rounded-md px-6 bg-[#1a2e05] hover:bg-[#2a450a] text-white">
                Subscribe
              </Button>
            </div>
          </motion.div>
        </div>

        {/* Divider & Sub-links */}
        <motion.div {...fadeUp(0.2)} className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 pt-10 pb-16 border-t border-border/40">
          <div className="flex flex-wrap gap-8">
            <a href="#" className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors uppercase tracking-wider">Terms of Use</a>
            <a href="#" className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors uppercase tracking-wider">Privacy Policy</a>
          </div>
          
          <div className="flex flex-col md:flex-row items-start md:items-center gap-6 lg:gap-12">
            <span className="text-xs text-muted-foreground uppercase tracking-wider">
              Designed by <span className="text-foreground">@Dishant-Gotis</span>
            </span>
            <div className="flex items-center gap-6 text-foreground/80">
              <a href="#" className="hover:text-accent transition-colors"><LinkedinIcon /></a>
              <a href="#" className="hover:text-accent transition-colors"><XIcon /></a>
              <a href="#" className="hover:text-accent transition-colors"><InstagramIcon /></a>
            </div>
          </div>
        </motion.div>

        {/* Links Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-12 mb-20">
          <motion.div {...fadeUp(0.3)}>
            <h5 className="text-sm font-bold text-foreground mb-6">Product</h5>
            <ul className="space-y-4">
              <FooterLink href="#features">Calendar</FooterLink>
              <FooterLink href="#how-it-works">Meetings</FooterLink>
              <FooterLink href="#">Notes & Briefs</FooterLink>
              <FooterLink href="#">Project Spaces</FooterLink>
              <FooterLink href="#">Workspaces</FooterLink>
            </ul>
          </motion.div>

          <motion.div {...fadeUp(0.35)}>
            <h5 className="text-sm font-bold text-foreground mb-6">Industry</h5>
            <ul className="space-y-4">
              <FooterLink href="#">Freelancers</FooterLink>
              <FooterLink href="#">Clients</FooterLink>
              <FooterLink href="#">Studios</FooterLink>
              <FooterLink href="#">Startups</FooterLink>
            </ul>
          </motion.div>

          <div className="flex flex-col gap-12 col-span-2 md:col-span-1">
            <motion.div {...fadeUp(0.4)} className="space-y-6">
              <h5 className="text-lg font-bold text-foreground hover:text-accent cursor-pointer transition-colors">Pricing</h5>
              <h5 className="text-lg font-bold text-foreground hover:text-accent cursor-pointer transition-colors">Resources</h5>
              <h5 className="text-lg font-bold text-foreground hover:text-accent cursor-pointer transition-colors">Contact</h5>
              <h5 className="text-lg font-bold text-foreground hover:text-accent cursor-pointer transition-colors">For Investors</h5>
            </motion.div>
          </div>
        </div>

        {/* Brand Illustration */}
        <motion.div
           initial={{ opacity: 0, scale: 0.95 }}
           whileInView={{ opacity: 1, scale: 1 }}
           viewport={{ once: true }}
           transition={{ duration: 1.2, ease: [0.25, 0.46, 0.45, 0.94] }}
           className="w-full relative mt-16"
        >
          <video
            src="/images/footer-vid.mp4"
            autoPlay
            muted
            loop
            playsInline
            className="w-full h-auto relative z-10"
          />
        </motion.div>

        {/* Bottom Copyright */}
        <motion.div 
          {...fadeUp(0.5)}
          className="text-center pt-8 border-t border-border/20 mt-10"
        >
          <p className="text-xs text-muted-foreground">
            {currentYear} &copy; MailMind. All rights reserved.
          </p>
        </motion.div>
      </div>

      {/* Background Decorative Element */}
      <div className="absolute top-0 right-0 -translate-y-1/2 translate-x-1/4 w-[600px] h-[600px] bg-accent/5 rounded-full blur-[100px] pointer-events-none -z-10" />
    </footer>
  );
}
