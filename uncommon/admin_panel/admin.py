from django.contrib import admin
from .models import *


admin.site.register(Admin)
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(VendorBill)
admin.site.register(VendorPayment)
admin.site.register(VendorBillLine)
admin.site.register(VendorPaymentAllocation)
admin.site.register(Supplier)
admin.site.register(PurchaseOrder)
admin.site.register(PurchaseOrderLine)