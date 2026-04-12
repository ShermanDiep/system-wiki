#import "Store.h"

@implementation Store
+ (Store *)shared {
  return [Store new];
}
@end
