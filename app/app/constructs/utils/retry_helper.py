"""
Retry Strategy Helper
Provides exponential backoff and retry budget functionality for Lambda functions
"""
import time
import random
import logging
from typing import Callable, Any, Optional, Dict
from functools import wraps
from botocore.exceptions import ClientError


logger = logging.getLogger()


class RetryBudget:
    """Manages retry budgets to prevent resource exhaustion"""
    
    def __init__(self, max_retries: int = 10, time_window: int = 300):
        self.max_retries = max_retries
        self.time_window = time_window
        self._retry_counts: Dict[str, list] = {}
    
    def can_retry(self, service_name: str) -> bool:
        """Check if retries are available for a service"""
        now = time.time()
        
        # Clean old retry records
        if service_name in self._retry_counts:
            self._retry_counts[service_name] = [
                timestamp for timestamp in self._retry_counts[service_name]
                if now - timestamp < self.time_window
            ]
        else:
            self._retry_counts[service_name] = []
        
        return len(self._retry_counts[service_name]) < self.max_retries
    
    def record_retry(self, service_name: str) -> None:
        """Record a retry attempt"""
        now = time.time()
        if service_name not in self._retry_counts:
            self._retry_counts[service_name] = []
        
        self._retry_counts[service_name].append(now)
        logger.info(f"Retry recorded for {service_name}. Count: {len(self._retry_counts[service_name])}/{self.max_retries}")


class ExponentialBackoff:
    """Implements exponential backoff with jitter"""
    
    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0, 
                 backoff_multiplier: float = 2.0, jitter: bool = True):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number"""
        delay = min(self.base_delay * (self.backoff_multiplier ** attempt), self.max_delay)
        
        if self.jitter:
            # Add jitter to prevent thundering herd
            delay *= (0.5 + random.random() * 0.5)
        
        return delay


class RetryHelper:
    """Main retry helper for Lambda functions"""
    
    def __init__(self):
        self.retry_budget = RetryBudget()
        self.backoff = ExponentialBackoff()
    
    
    def retry_simple(
        self,
        max_attempts: int = 3,
        delay: float = 1.0,
        backoff_multiplier: float = 2.0,
        retryable_exceptions: tuple = (ClientError,)
    ):
        """Simple retry decorator"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                last_exception = None
                current_delay = delay
                
                for attempt in range(max_attempts):
                    try:
                        return func(*args, **kwargs)
                    
                    except retryable_exceptions as e:
                        last_exception = e
                        
                        if attempt == max_attempts - 1:
                            break
                        
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {current_delay:.2f} seconds...")
                        time.sleep(current_delay)
                        current_delay *= backoff_multiplier
                    
                    except Exception as e:
                        logger.error(f"Non-retryable error: {e}")
                        raise
                
                logger.error(f"All {max_attempts} attempts failed")
                raise last_exception
            
            return wrapper
        return decorator


class RetryBudgetExhaustedError(Exception):
    """Exception raised when retry budget is exhausted"""
    pass


# Global instance for easy use
retry_helper = RetryHelper()


def retry_simple(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    retryable_exceptions: tuple = (ClientError,)
):
    """Convenience function for simple retries"""
    return retry_helper.retry_simple(max_attempts, delay, backoff_multiplier, retryable_exceptions)


