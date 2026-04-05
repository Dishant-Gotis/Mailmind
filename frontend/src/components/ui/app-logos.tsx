import React from "react";

export const SlackLogo = ({ className, title }: { className?: string; title?: string }) => (
  <img 
    src="/images/Slack-Logo-PNG-File.webp" 
    alt="Slack Logo" 
    className={`object-contain ${className || ""}`} 
    title={title}
  />
);

export const GmailLogo = ({ className, title }: { className?: string; title?: string }) => (
  <img 
    src="/images/gmail-email-logo-icon-free-png.webp" 
    alt="Gmail Logo" 
    className={`object-contain ${className || ""}`} 
    title={title}
  />
);

export const GoogleMeetLogo = ({ className, title }: { className?: string; title?: string }) => (
  <img 
    src="/images/google-meet-icon-logo-symbol-free-png.webp" 
    alt="Google Meet Logo" 
    className={`object-contain ${className || ""}`} 
    title={title}
  />
);

export const GoogleCalendarLogo = ({ className, title }: { className?: string; title?: string }) => (
  <img 
    src="/images/google-calendar-icon-logo-symbol-free-png.webp" 
    alt="Google Calendar Logo" 
    className={`object-contain ${className || ""}`} 
    title={title}
  />
);


