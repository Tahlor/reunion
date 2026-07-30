// Public, non-secret configuration for the Hazard reunion site.
window.REUNION_CONFIG = {
  rsvpFormUrl: 'https://docs.google.com/forms/d/e/1FAIpQLSecJufXG9xkJcm1XU42xkS6POYb6eIS4GHTvy77bd_KBOfbGw/viewform'
};

// The destinations are SSO-protected. The links can be public because access is
// enforced by the reunion service, not by obscurity.
document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('reunionAdminLinks')) return;
  const footer = document.querySelector('footer.sources');
  if (!footer) return;
  const links = document.createElement('div');
  links.id = 'reunionAdminLinks';
  links.style.cssText = 'margin-top:14px;font-size:.84rem;opacity:.78';
  links.innerHTML = '<a href="/reunion/rsvp/">Meal RSVP</a> · <a href="/reunion/edit">Edit this page</a> · <a href="/reunion/admin">Admin chat</a>';
  footer.appendChild(links);
});
