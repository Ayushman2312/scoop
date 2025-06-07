/**
 * Blogify Image Loader
 * Loads images from Unsplash API based on search terms
 */

document.addEventListener('DOMContentLoaded', function() {
    // Find all images with data-search-terms attribute
    const imagesToLoad = document.querySelectorAll('img.unsplash-image[data-search-terms]');
    
    if (imagesToLoad.length === 0) return;
    
    // Load images one by one with a slight delay to avoid rate limiting
    let index = 0;
    const loadNextImage = () => {
        if (index >= imagesToLoad.length) return;
        
        const img = imagesToLoad[index];
        const searchTerms = img.getAttribute('data-search-terms');
        const isFeatured = img.getAttribute('data-placeholder') === 'featured';
        
        // Make the API call to Unsplash
        fetchUnsplashImage(searchTerms, img, isFeatured)
            .then(() => {
                // Load next image after a short delay
                setTimeout(() => {
                    index++;
                    loadNextImage();
                }, 500);
            })
            .catch(err => {
                console.error('Error loading image:', err);
                // Continue to next image even if there's an error
                setTimeout(() => {
                    index++;
                    loadNextImage();
                }, 500);
            });
    };
    
    // Start loading images
    loadNextImage();
});

/**
 * Fetches an image from Unsplash based on search terms
 * @param {string} searchTerms - The search query
 * @param {HTMLImageElement} imgElement - The image element to update
 * @param {boolean} isFeatured - Whether this is a featured (larger) image
 */
async function fetchUnsplashImage(searchTerms, imgElement, isFeatured = false) {
    try {
        // Use Unsplash Source API which doesn't require API key
        // Format: https://source.unsplash.com/featured/?nature,water
        const width = isFeatured ? 1200 : 800;
        const height = isFeatured ? 600 : 500;
        
        // Clean search terms
        const cleanTerms = searchTerms.replace(/[^\w\s,]/g, '')
            .replace(/\s+/g, ',')
            .toLowerCase();
        
        // Create URL for Unsplash Source
        const unsplashUrl = `https://source.unsplash.com/featured/${width}x${height}/?${cleanTerms}`;
        
        // Set the image source
        imgElement.src = unsplashUrl;
        
        // Remove placeholder styling once loaded
        imgElement.onload = () => {
            imgElement.classList.remove('unsplash-image');
            imgElement.style.minHeight = 'auto';
            imgElement.style.backgroundColor = 'transparent';
            imgElement.style.border = 'none';
        };
        
        return true;
    } catch (error) {
        console.error('Error fetching Unsplash image:', error);
        return false;
    }
}

/**
 * Fallback function to use a different image service if Unsplash fails
 */
function useFallbackImageService(searchTerms, imgElement, isFeatured) {
    // Default placeholder image from placehold.co if all else fails
    const width = isFeatured ? 1200 : 800;
    const height = isFeatured ? 600 : 500;
    
    imgElement.src = `https://placehold.co/${width}x${height}/CCCCCC/666666?text=${encodeURIComponent(searchTerms)}`;
    
    // Remove placeholder styling
    imgElement.classList.remove('unsplash-image');
    imgElement.style.minHeight = 'auto';
    imgElement.style.backgroundColor = 'transparent';
    imgElement.style.border = 'none';
} 