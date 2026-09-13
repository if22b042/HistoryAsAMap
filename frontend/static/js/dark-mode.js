// Dark Mode Toggle Functionality
console.log('Dark mode script loaded');

(function() {
    console.log('Dark mode IIFE executing');
    
    // Check for saved user preference
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    console.log('Saved theme:', savedTheme, 'Prefers dark:', prefersDark);
    
    // Set initial theme
    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
        document.body.classList.add('dark-mode');
        console.log('Dark mode enabled on load');
    }
    
    // Toggle dark mode
    function toggleDarkMode() {
        console.log('Toggle dark mode called');
        document.body.classList.toggle('dark-mode');
        
        // Save preference
        if (document.body.classList.contains('dark-mode')) {
            localStorage.setItem('theme', 'dark');
            console.log('Theme set to dark');
        } else {
            localStorage.setItem('theme', 'light');
            console.log('Theme set to light');
        }
    }
    
    // Make function globally available
    window.toggleDarkMode = toggleDarkMode;
    console.log('toggleDarkMode function attached to window');
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem('theme')) {
            if (e.matches) {
                document.body.classList.add('dark-mode');
            } else {
                document.body.classList.remove('dark-mode');
            }
        }
    });
    
    // Initialize toggle button if it exists
    document.addEventListener('DOMContentLoaded', function() {
        console.log('DOM Content Loaded');
        const darkModeToggle = document.getElementById('dark-mode-toggle');
        console.log('Dark mode toggle button found:', darkModeToggle);
        
        if (darkModeToggle) {
            darkModeToggle.addEventListener('click', toggleDarkMode);
            console.log('Click event listener attached to toggle button');
            
            // Update icon based on current theme
            updateDarkModeIcon();
        } else {
            console.error('Dark mode toggle button not found!');
        }
    });
    
    // Update dark mode icon
    function updateDarkModeIcon() {
        const darkModeToggle = document.getElementById('dark-mode-toggle');
        if (!darkModeToggle) return;
        
        const icon = darkModeToggle.querySelector('i');
        if (icon) {
            if (document.body.classList.contains('dark-mode')) {
                icon.classList.remove('fa-moon');
                icon.classList.add('fa-sun');
            } else {
                icon.classList.remove('fa-sun');
                icon.classList.add('fa-moon');
            }
        }
    }
    
    // Update icon when theme changes
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.attributeName === 'class') {
                updateDarkModeIcon();
            }
        });
    });
    
    observer.observe(document.body, { attributes: true });
})();
