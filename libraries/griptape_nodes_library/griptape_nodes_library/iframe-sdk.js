/**
 * Griptape Nodes Iframe SDK
 * A simple SDK for creating iframe components that communicate with the parent window
 */

class IframeComponent {
    constructor(options = {}) {
        this.currentValue = null;
        this.hasReceivedInitialValue = false;
        this.isReceivingFromParent = false;
        this.onValueChange = options.onValueChange || (() => {});
        this.onReady = options.onReady || (() => {});
        this.onError = options.onError || (() => {});
        this.componentName = options.componentName || 'Component';
        this.defaultValue = options.defaultValue;
        
        this.init();
    }
    
    init() {
        // Set up message listener
        window.addEventListener('message', this.handleParentMessage.bind(this));
        
        // Notify parent that we're ready
        setTimeout(() => {
            this.sendReadyMessage();
        }, 100);
        
        console.log(`${this.componentName} iframe loaded - waiting for parent value...`);
    }
    
    // Send ready message to parent
    sendReadyMessage() {
        try {
            window.parent.postMessage({
                type: 'IFRAME_READY',
                message: `${this.componentName} is ready to receive values`
            }, '*');
        } catch (error) {
            console.warn('Could not send ready message to parent:', error);
            this.onError('Failed to send ready message');
        }
    }
    
    // Send value update to parent
    sendValueUpdate(value) {
        // Don't send if we're receiving from parent
        if (this.isReceivingFromParent) {
            console.log('Skipping send to parent - receiving from parent');
            return;
        }
        
        try {
            const message = {
                type: 'VALUE_UPDATE',
                value: value
            };
            
            window.parent.postMessage(message, '*');
            console.log(`Sent value: ${value}`);
            
        } catch (error) {
            console.error('Failed to send message to parent:', error);
            this.onError('Error sending message to parent');
        }
    }
    
    // Handle messages from parent
    handleParentMessage(event) {
        console.log('Iframe received message:', event.data);
        
        try {
            const { type, value, label } = event.data;
            
            if (type === 'SET_VALUE') {
                console.log('Received SET_VALUE from parent:', value);
                
                // Mark that we're receiving from parent
                this.isReceivingFromParent = true;
                
                // Update our value
                if (value !== null && value !== undefined) {
                    this.currentValue = value;
                    console.log(`Received value from parent: ${value}`);
                } else {
                    // Handle null/undefined values
                    this.currentValue = this.defaultValue || '';
                    console.log('Received empty value from parent');
                }
                
                this.hasReceivedInitialValue = true;
                
                // Call the value change handler
                this.onValueChange(this.currentValue);
                
                // Reset the flag immediately after updating
                this.isReceivingFromParent = false;
                
            } else {
                console.log('Received message with type:', type);
            }
            
        } catch (error) {
            console.error('Failed to process message from parent:', error);
            this.onError('Error processing message from parent');
        }
    }
    
    // Update value (call this when user changes the value)
    updateValue(value) {
        this.currentValue = value;
        this.sendValueUpdate(value);
    }
    
    // Get current value
    getValue() {
        return this.currentValue;
    }
    
    // Check if we've received initial value
    hasInitialValue() {
        return this.hasReceivedInitialValue;
    }
}

// Utility functions for common UI patterns
const UIUtils = {
    // Show loading state
    showLoading() {
        const loadingState = document.getElementById('loadingState');
        const mainContent = document.getElementById('mainContent');
        if (loadingState) loadingState.classList.remove('hidden');
        if (mainContent) mainContent.classList.add('hidden');
    },
    
    // Show main content and hide loading
    showMainContent() {
        const loadingState = document.getElementById('loadingState');
        const mainContent = document.getElementById('mainContent');
        if (loadingState) loadingState.classList.add('hidden');
        if (mainContent) mainContent.classList.remove('hidden');
    },
    
    // Update status display
    updateStatus(message) {
        const statusElement = document.getElementById('statusText');
        if (statusElement) {
            statusElement.textContent = message;
        }
        console.log('Status:', message);
    },
    
    // Create loading spinner HTML
    createLoadingSpinner() {
        return `
            <div class="loading">
                <div class="loading-spinner"></div>
                <div>Waiting for parent value...</div>
            </div>
        `;
    },
    
    // Create status display HTML
    createStatusDisplay() {
        return `
            <div class="status" id="status">
                <strong>Status:</strong> <span id="statusText">Ready</span>
            </div>
        `;
    }
};

// Common CSS styles
const CommonStyles = `
    .loading {
        text-align: center;
        padding: 40px 20px;
        color: #666;
    }
    
    .loading-spinner {
        width: 20px;
        height: 20px;
        border: 2px solid #f3f3f3;
        border-top: 2px solid #3498db;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 10px;
    }
    
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    .status {
        background: #e8f5e8;
        border: 1px solid #4caf50;
        border-radius: 4px;
        padding: 8px;
        margin-top: 15px;
        font-size: 12px;
        text-align: center;
    }
    
    .hidden {
        display: none;
    }
    
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        margin: 0;
        padding: 20px;
        background: #f5f5f5;
        color: #333;
    }
    
    .container {
        max-width: 300px;
        margin: 0 auto;
        background: white;
        border-radius: 8px;
        padding: 20px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
`;

// Export for use in components
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { IframeComponent, UIUtils, CommonStyles };
} else {
    window.IframeComponent = IframeComponent;
    window.UIUtils = UIUtils;
    window.CommonStyles = CommonStyles;
} 