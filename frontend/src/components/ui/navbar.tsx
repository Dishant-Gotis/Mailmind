"use client";

import React, { useState, useEffect, useRef } from 'react';
import { Button } from './button';

const AnimatedNavLink = ({ href, children }: { href: string; children: React.ReactNode }) => {
  return (
    <a
      href={href}
      className="relative text-sm text-muted-foreground hover:text-foreground transition-colors duration-200 after:absolute after:bottom-[-2px] after:left-0 after:w-0 after:h-[1.5px] after:bg-foreground after:transition-all after:duration-300 hover:after:w-full"
    >
      {children}
    </a>
  );
};

export function Navbar() {
  const [isOpen, setIsOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [headerShapeClass, setHeaderShapeClass] = useState('rounded-full');
  const shapeTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const toggleMenu = () => {
    setIsOpen(!isOpen);
  };

  /* ─── Track scroll for subtle backdrop intensification ─── */
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    if (shapeTimeoutRef.current) {
      clearTimeout(shapeTimeoutRef.current);
    }

    if (isOpen) {
      setHeaderShapeClass('rounded-2xl');
    } else {
      shapeTimeoutRef.current = setTimeout(() => {
        setHeaderShapeClass('rounded-full');
      }, 300);
    }

    return () => {
      if (shapeTimeoutRef.current) {
        clearTimeout(shapeTimeoutRef.current);
      }
    };
  }, [isOpen]);

  const logoElement = (
    <div className="relative w-7 h-7 flex items-center justify-center">
      <span className="absolute w-1.5 h-1.5 rounded-full bg-accent top-0 left-1/2 transform -translate-x-1/2"></span>
      <span className="absolute w-1.5 h-1.5 rounded-full bg-accent left-0 top-1/2 transform -translate-y-1/2"></span>
      <span className="absolute w-1.5 h-1.5 rounded-full bg-accent right-0 top-1/2 transform -translate-y-1/2"></span>
      <span className="absolute w-1.5 h-1.5 rounded-full bg-accent bottom-0 left-1/2 transform -translate-x-1/2"></span>
    </div>
  );

  const navLinksData = [
    { label: 'How it works', href: '#how-it-works' },
    { label: 'Features', href: '#features' },
    { label: 'FAQ', href: '#faq' },
  ];

  return (
    <header
      className={`fixed top-5 left-1/2 transform -translate-x-1/2 z-50
                   flex flex-col items-center
                   pl-5 pr-5 py-2.5
                   ${headerShapeClass}
                   w-[calc(100%-2rem)] sm:w-auto
                   transition-all duration-300 ease-in-out`}
      style={{
        background: scrolled
          ? 'rgba(255, 255, 255, 0.35)'
          : 'rgba(255, 255, 255, 0.15)',
        backdropFilter: 'blur(24px) saturate(1.8)',
        WebkitBackdropFilter: 'blur(24px) saturate(1.8)',
        border: '1px solid rgba(255, 255, 255, 0.3)',
        boxShadow: scrolled
          ? '0 8px 32px rgba(0, 0, 0, 0.08), 0 2px 8px rgba(0, 0, 0, 0.04), inset 0 1px 0 rgba(255, 255, 255, 0.4)'
          : '0 4px 16px rgba(0, 0, 0, 0.05), inset 0 1px 0 rgba(255, 255, 255, 0.2)',
      }}
    >

      <div className="flex items-center justify-between w-full gap-x-6 sm:gap-x-8">
        <a href="#" className="flex items-center gap-2 group">
           {logoElement}
           <span className="text-base font-semibold tracking-tight text-foreground group-hover:text-accent transition-colors duration-200">
            MailMind
           </span>
        </a>

        <nav className="hidden md:flex items-center space-x-6 text-sm">
          {navLinksData.map((link) => (
            <AnimatedNavLink key={link.href} href={link.href}>
              {link.label}
            </AnimatedNavLink>
          ))}
        </nav>

        <div className="hidden md:flex items-center gap-2.5">
          <Button variant="ghost" size="sm" className="rounded-full text-sm">
            Log In
          </Button>
          <Button
            size="sm"
            className="rounded-full text-sm"
            style={{
              background: 'rgba(99, 102, 241, 0.9)',
              backdropFilter: 'blur(4px)',
            }}
          >
            Get Started
          </Button>
        </div>

        <button className="md:hidden flex items-center justify-center w-8 h-8 text-foreground focus:outline-none" onClick={toggleMenu} aria-label={isOpen ? 'Close Menu' : 'Open Menu'}>
          {isOpen ? (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
          ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
          )}
        </button>
      </div>

      <div className={`md:hidden flex flex-col items-center w-full transition-all ease-in-out duration-300 overflow-hidden
                       ${isOpen ? 'max-h-[1000px] opacity-100 pt-4' : 'max-h-0 opacity-0 pt-0 pointer-events-none'}`}>
        <nav className="flex flex-col items-center space-y-4 text-base w-full">
          {navLinksData.map((link) => (
            <a key={link.href} href={link.href} className="text-muted-foreground hover:text-foreground transition-colors w-full text-center">
              {link.label}
            </a>
          ))}
        </nav>
        <div className="flex flex-col items-center space-y-3 mt-4 w-full">
          <Button variant="ghost" size="sm" className="rounded-full w-full">
            Log In
          </Button>
          <Button size="sm" className="rounded-full w-full">
            Get Started
          </Button>
        </div>
      </div>
    </header>
  );
}