#import "Service.h"

@implementation Service
- (Store *)run {
  return [Store shared];
}
@end
