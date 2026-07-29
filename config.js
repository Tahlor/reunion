// Public, non-secret configuration for the Hazard reunion site.
// The Archimedes setup agent will replace the empty string after creating the form.
window.REUNION_CONFIG = {
  rsvpFormUrl: ''
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
  links.innerHTML = '<a href="/reunion/edit">Edit this page</a> · <a href="/reunion/admin">Admin chat</a>';
  footer.appendChild(links);
});
