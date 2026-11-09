
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from admin_panel.models import Product


IMAGE_FIELDS = ["image", "image2", "image3", "image4"]


class Command(BaseCommand):
    help = "Migrate existing product images to Cloudinary"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Check images without uploading or modifying records."
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        products = Product.objects.all()
        uploaded = 0
        skipped = 0
        failed = 0

        self.stdout.write(
            self.style.SUCCESS(
                f"Found {products.count()} products."
            )
        )

        for product in products:
            self.stdout.write(
                f"\nProcessing: {product.product_name}"
            )

            for field in IMAGE_FIELDS:
                image = getattr(product, field)

                if not image:
                    continue

                image_name = image.name

                # Skip images already stored in Cloudinary.
                if image_name.startswith("http://") or image_name.startswith("https://"):
                    self.stdout.write(
                        f"  SKIPPED {field}: Already a URL"
                    )
                    skipped += 1
                    continue

                local_path = Path(settings.MEDIA_ROOT) / image_name

                if not local_path.is_file():
                    self.stdout.write(
                        self.style.WARNING(
                            f"  MISSING {field}: {local_path}"
                        )
                    )
                    failed += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f"  READY {field}: {image_name}"
                    )
                    continue

                try:
                    # Upload using the configured Django storage backend.
                    with local_path.open("rb") as file:
                        getattr(product, field).save(
                            local_path.name,
                            File(file),
                            save=False
                        )

                    # Persist the new Cloudinary storage reference.
                    with transaction.atomic():
                        product.save(
                            update_fields=[field]
                        )

                    uploaded += 1

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  UPLOADED {field}: {image_name}"
                        )
                    )

                except Exception as exc:
                    failed += 1
                    self.stderr.write(
                        self.style.ERROR(
                            f"  FAILED {field}: {exc}"
                        )
                    )

        self.stdout.write("\n--- MIGRATION SUMMARY ---")
        self.stdout.write(f"Uploaded: {uploaded}")
        self.stdout.write(f"Skipped: {skipped}")
        self.stdout.write(f"Missing/Failed: {failed}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Dry run completed. No changes were made."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Migration process completed."
                )
            )
